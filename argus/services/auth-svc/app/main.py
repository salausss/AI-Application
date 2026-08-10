import os
import time
import asyncpg
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from jose import jwt, JWTError

app = FastAPI(title="auth-svc", version="0.1.0")

DATABASE_URL = os.environ["DATABASE_URL"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL_SECONDS = 15 * 60
REFRESH_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _pool


def create_token(user_id: str, role: str, ttl: int) -> str:
    payload = {"sub": user_id, "role": role, "exp": int(time.time()) + ttl}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(creds: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    try:
        return jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/v1/auth/register")
async def register(req: RegisterRequest):
    pool = await get_pool()
    password_hash = pwd_context.hash(req.password)
    async with pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT id FROM users WHERE email = $1", req.email)
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")
        user_id = await conn.fetchval(
            "INSERT INTO users (email, password_hash) VALUES ($1, $2) RETURNING id",
            req.email, password_hash,
        )
    return {"user_id": str(user_id)}


@app.post("/api/v1/auth/login")
async def login(req: LoginRequest):
    pool = await get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id, password_hash, role FROM users WHERE email = $1", req.email
        )
    if not user or not pwd_context.verify(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_token(str(user["id"]), user["role"], ACCESS_TOKEN_TTL_SECONDS)
    refresh_token = create_token(str(user["id"]), user["role"], REFRESH_TOKEN_TTL_SECONDS)
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


@app.get("/api/v1/auth/me")
async def me(payload: dict = Depends(verify_token)):
    return {"user_id": payload["sub"], "role": payload["role"]}


# --- TODO (Day 2 hands-on) ---
# - /api/v1/auth/refresh -> exchange a valid refresh_token for a new access_token
# - Rate limit /login (slowapi) to blunt brute-force attempts — good security-protocol talking point
# - Share `verify_token` logic with chat-svc/ingestion-svc — either via a shared package,
#   or (simpler for now) re-verify the JWT independently in each service using the same JWT_SECRET
