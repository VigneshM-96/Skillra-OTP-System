"""
OTP core logic.

Redis key layout:
  otp:{email}:hash       → bcrypt hash of the OTP         (TTL = otp_expire_seconds)
  otp:{email}:attempts   → wrong-attempt counter           (TTL = otp_expire_seconds)
  otp:{email}:cooldown   → exists while resend is blocked  (TTL = otp_cooldown_seconds)
"""

import secrets
import hashlib
import time
from enum import Enum

import redis.asyncio as aioredis

from config import get_settings

settings = get_settings()


class VerifyResult(str, Enum):
    SUCCESS = "success"
    INVALID = "invalid"
    EXPIRED = "expired"
    MAX_ATTEMPTS = "max_attempts"


# ── Key helpers ──────────────────────────────────────────────────────────────

def _key_hash(email: str) -> str:
    return f"otp:{email}:hash"

def _key_attempts(email: str) -> str:
    return f"otp:{email}:attempts"

def _key_cooldown(email: str) -> str:
    return f"otp:{email}:cooldown"


# ── Hash helpers (SHA-256 — fast enough for short-lived 6-digit OTPs) ────────

def _hash_otp(otp: str) -> str:
    """Store a SHA-256 digest instead of plaintext."""
    return hashlib.sha256(otp.encode()).hexdigest()


# ── Public API ────────────────────────────────────────────────────────────────

async def generate_and_store_otp(
    redis: aioredis.Redis,
    email: str,
) -> tuple[str, bool]:
    """
    Generate a fresh OTP and persist it in Redis.

    Returns (otp_plaintext, was_rate_limited).
    If rate-limited, returns ("", True) — caller should NOT send email.
    """
    cooldown_key = _key_cooldown(email)
    if await redis.exists(cooldown_key):
        return "", True

    # Cryptographically secure N-digit OTP
    otp = "".join(
        [str(secrets.randbelow(10)) for _ in range(settings.otp_length)]
    )

    pipe = redis.pipeline()
    pipe.set(_key_hash(email), _hash_otp(otp), ex=settings.otp_expire_seconds)
    pipe.delete(_key_attempts(email))                         # reset attempts
    pipe.set(_key_cooldown(email), "1", ex=settings.otp_cooldown_seconds)
    await pipe.execute()

    return otp, False


async def verify_otp(
    redis: aioredis.Redis,
    email: str,
    otp: str,
) -> VerifyResult:
    """
    Verify an OTP.  On success the keys are deleted immediately (single-use).
    On failure the attempt counter is incremented; too many → locked.
    """
    hash_key     = _key_hash(email)
    attempts_key = _key_attempts(email)

    stored_hash = await redis.get(hash_key)

    if stored_hash is None:
        return VerifyResult.EXPIRED

    # Check brute-force counter BEFORE comparing
    attempts = int(await redis.get(attempts_key) or 0)
    if attempts >= settings.otp_max_attempts:
        return VerifyResult.MAX_ATTEMPTS

    if _hash_otp(otp) == stored_hash:
        # Valid — delete all keys immediately (one-time use)
        pipe = redis.pipeline()
        pipe.delete(hash_key)
        pipe.delete(attempts_key)
        await pipe.execute()
        return VerifyResult.SUCCESS

    # Wrong OTP — increment attempts counter, keep same TTL as the OTP
    ttl = await redis.ttl(hash_key)
    await redis.set(attempts_key, attempts + 1, ex=max(ttl, 1))
    return VerifyResult.INVALID


async def get_otp_status(redis: aioredis.Redis, email: str) -> dict:
    """Debug / introspection helper (disable in production)."""
    hash_ttl     = await redis.ttl(_key_hash(email))
    attempts     = await redis.get(_key_attempts(email))
    cooldown_ttl = await redis.ttl(_key_cooldown(email))
    return {
        "has_active_otp": hash_ttl > 0,
        "expires_in_seconds": max(hash_ttl, 0),
        "wrong_attempts": int(attempts or 0),
        "resend_cooldown_seconds": max(cooldown_ttl, 0),
    }