import os
import json
import logging
import httpx
import boto3
import asyncpg
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from uuid import UUID, uuid4
import time
from prometheus_client import Counter, Histogram, make_asgi_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chat-svc")

app = FastAPI(title="chat-svc", version="0.1.0")

RETRIEVAL_LATENCY = Histogram("retrieval_call_duration_seconds", "Time spent calling retrieval-svc")
BEDROCK_LATENCY = Histogram("bedrock_invoke_duration_seconds", "Time spent in Bedrock invoke_model")
TOKEN_USAGE = Counter("bedrock_tokens_total", "Total tokens used", ["type"])

app.mount("/metrics", make_asgi_app())

DATABASE_URL = os.environ["DATABASE_URL"]
RETRIEVAL_URL = os.environ.get("RETRIEVAL_URL", "http://retrieval-svc:8000")
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "global.anthropic.claude-sonnet-4-5-20250929-v1:0")

bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _pool


class ChatRequest(BaseModel):
    session_id: UUID | None = None
    message: str


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/v1/chat")
async def chat(req: ChatRequest):
    pool = await get_pool()

    session_id = req.session_id or uuid4()
    async with pool.acquire() as conn:
        # create session if new
        existing = await conn.fetchrow("SELECT id FROM chat_sessions WHERE id = $1", session_id)
        if not existing:
            await conn.execute(
                "INSERT INTO chat_sessions (id, title) VALUES ($1, $2)",
                session_id, req.message[:60],
            )

        # 1. Retrieve relevant chunks
        async with httpx.AsyncClient(timeout=15.0) as client:
            retrieval_start = time.time()
            try:
                resp = await client.post(f"{RETRIEVAL_URL}/api/v1/search", json={"query": req.message, "top_k": 5})
                resp.raise_for_status()
                chunks = resp.json().get("results", [])
                RETRIEVAL_LATENCY.observe(time.time() - retrieval_start)
            except httpx.HTTPError as e:
                logger.error(f"retrieval-svc call failed: {e}")
                chunks = []

        context_text = "\n\n".join(f"[{i+1}] {c['content']}" for i, c in enumerate(chunks))
        citations = [{"chunk_id": c["chunk_id"], "document_id": c.get("document_id")} for c in chunks]

        # 2. Build grounded prompt
        if context_text:
            system_prompt = (
                "Answer ONLY using the numbered context below. Cite sources like [1], [2]. "
                "If the context doesn't contain the answer, say you don't have that information — do not guess.\n\n"
                f"Context:\n{context_text}"
            )
        else:
            system_prompt = "No relevant context was found. Tell the user you don't have information on this topic."

        # 3. Call Bedrock Claude
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": [{"role": "user", "content": req.message}],
        }
        bedrock_start = time.time()
        try:
            bedrock_resp = bedrock.invoke_model(modelId=BEDROCK_MODEL_ID, body=json.dumps(body))
            result = json.loads(bedrock_resp["body"].read())
            answer = result["content"][0]["text"]
            BEDROCK_LATENCY.observe(time.time() - bedrock_start)

            usage = result.get("usage", {})
            TOKEN_USAGE.labels(type="input").inc(usage.get("input_tokens", 0))
            TOKEN_USAGE.labels(type="output").inc(usage.get("output_tokens", 0))
        except Exception as e:
            logger.error(f"Bedrock call failed: {e}")
            raise HTTPException(status_code=502, detail="LLM call failed") from e

        # 4. Persist
        await conn.execute(
            "INSERT INTO messages (session_id, role, content) VALUES ($1, 'user', $2)",
            session_id, req.message,
        )
        await conn.execute(
            "INSERT INTO messages (session_id, role, content, citations) VALUES ($1, 'assistant', $2, $3)",
            session_id, answer, json.dumps(citations),
        )

    return {"session_id": str(session_id), "answer": answer, "citations": citations}


# --- TODO (your Day 2 hands-on work, don't skip writing this yourself) ---
# - GET /api/v1/sessions/{session_id}/messages  -> fetch history for the UI sidebar
# - WebSocket /ws/chat -> stream tokens instead of returning the full answer at once
# - JWT dependency on this route once auth-svc is wired in (see auth-svc/app/main.py)
