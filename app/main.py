from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import router
from redis_client import get_redis, close_redis
from config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ─────────────────────────────────────────
    redis = await get_redis()
    await redis.ping()          # fail fast if Redis is unreachable
    print("✅  Redis connected")
    yield
    # ── Shutdown ────────────────────────────────────────
    await close_redis()
    print("🔌  Redis disconnected")


app = FastAPI(
    title="OTP Service",
    description="Production-grade OTP via Email + Redis",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow Flutter app (or any origin in dev) — tighten in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.app_env != "production" else [
        # "https://yourdomain.com"
    ],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}