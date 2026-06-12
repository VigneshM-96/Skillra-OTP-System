from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
import redis.asyncio as aioredis

from app.otp import generate_and_store_otp, verify_otp, get_otp_status, VerifyResult
from app.email_sender import send_otp_email
from app.redis_client import get_redis
from app.config import get_settings

router   = APIRouter(prefix="/otp", tags=["OTP"])
settings = get_settings()


# ── Request / Response schemas ─────────────────────────────────────────────

class SendOTPRequest(BaseModel):
    email: EmailStr

class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str

class OTPResponse(BaseModel):
    success: bool
    message: str


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.post(
    "/send",
    response_model=OTPResponse,
    summary="Generate & email a one-time password",
)
async def send_otp(
    body: SendOTPRequest,
    redis: aioredis.Redis = Depends(get_redis),
):
    otp, rate_limited = await generate_and_store_otp(redis, body.email)

    if rate_limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Please wait {settings.otp_cooldown_seconds} seconds "
                "before requesting a new code."
            ),
        )

    try:
        await send_otp_email(body.email, otp)
    except Exception as exc:
        # Roll back Redis entry so the user can retry
        await redis.delete(f"otp:{body.email}:hash")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Email delivery failed: {exc}",
        )

    return OTPResponse(
        success=True,
        message=f"OTP sent to {body.email}. Valid for "
                f"{settings.otp_expire_seconds // 60} minutes.",
    )


@router.post(
    "/verify",
    response_model=OTPResponse,
    summary="Verify a one-time password",
)
async def verify_otp_endpoint(
    body: VerifyOTPRequest,
    redis: aioredis.Redis = Depends(get_redis),
):
    result = await verify_otp(redis, body.email, body.otp)

    match result:
        case VerifyResult.SUCCESS:
            return OTPResponse(success=True, message="OTP verified successfully.")

        case VerifyResult.EXPIRED:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="OTP has expired. Please request a new one.",
            )

        case VerifyResult.MAX_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Too many failed attempts. Please request a new OTP.",
            )

        case VerifyResult.INVALID:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OTP. Please check and try again.",
            )


# ── Debug endpoint (disable in production!) ───────────────────────────────

@router.get(
    "/status/{email}",
    summary="[DEV ONLY] Inspect OTP state for an email",
)
async def otp_status(
    email: str,
    redis: aioredis.Redis = Depends(get_redis),
):
    if settings.app_env == "production":
        raise HTTPException(status_code=404, detail="Not found.")
    return await get_otp_status(redis, email)