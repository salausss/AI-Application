import os
import io
import time
import json
import logging
import boto3
import chromadb
import weaviate
import asyncpg
from fastapi import FastAPI, UploadFile, File
from pypdf import PdfReader
from uuid import uuid4
from prometheus_client import Counter, Histogram, make_asgi_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ingestion-svc")

app = FastAPI(title="ingestion-svc", version="0.1.0")

SERVICE_NAME = "ingestion-svc"  # change per service: "auth-svc", "retrieval-svc", "ingestion-svc"

REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests",
    ["service", "method", "endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request latency",
    ["service", "method", "endpoint"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30]  # tuned for LLM-call-shaped latency, not typical web-request buckets
)

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration = time.time() - start
        endpoint = request.url.path
        REQUEST_COUNT.labels(service=SERVICE_NAME, method=request.method, endpoint=endpoint, status=status_code).inc()
        REQUEST_LATENCY.labels(service=SERVICE_NAME, method=request.method, endpoint=endpoint).observe(duration)

app.mount("/metrics", make_asgi_app())

DATABASE_URL = os.environ["DATABASE_URL"]

# --- SPOT 1: backend selection + client setup, replaces the old unconditional chroma_client lines ---
VECTOR_BACKEND = os.environ.get("VECTOR_BACKEND", "chroma")  # "chroma" or "weaviate"

CHROMA_HOST = os.environ.get("CHROMA_HOST", "chromadb")
CHROMA_PORT = int(os.environ.get("CHROMA_PORT", "8000"))
WEAVIATE_HOST = os.environ.get("WEAVIATE_HTTP_HOST", "weaviate")
WEAVIATE_PORT = int(os.environ.get("WEAVIATE_HTTP_PORT", "8080"))
WEAVIATE_GRPC_PORT = int(os.environ.get("WEAVIATE_GRPC_PORT_NUM", "50051"))

AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
EMBED_MODEL_ID = os.environ.get("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "argus_chunks")

CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200

bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)

collection = None
weaviate_client = None
weaviate_collection = None

if VECTOR_BACKEND == "chroma":
    chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    collection = chroma_client.get_or_create_collection(COLLECTION_NAME)
elif VECTOR_BACKEND == "weaviate":
    weaviate_client = weaviate.connect_to_custom(
        http_host=WEAVIATE_HOST, http_port=WEAVIATE_PORT, http_secure=False,
        grpc_host=WEAVIATE_HOST, grpc_port=WEAVIATE_GRPC_PORT, grpc_secure=False,
        skip_init_checks=True
    )
    weaviate_collection = weaviate_client.collections.get("ArgusChunk")

# --- end SPOT 1 ---

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _pool


def embed_text(text: str) -> list[float]:
    resp = bedrock.invoke_model(modelId=EMBED_MODEL_ID, body=json.dumps({"inputText": text}))
    return json.loads(resp["body"].read())["embedding"]


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start += size - overlap
    return [c.strip() for c in chunks if c.strip()]


def extract_text(filename: str, raw: bytes) -> str:
    if filename.lower().endswith(".pdf"):
        reader = PdfReader(io.BytesIO(raw))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return raw.decode("utf-8", errors="ignore")


@app.get("/health")
async def health():
    return {"status": "ok", "backend": VECTOR_BACKEND}


@app.post("/api/v1/documents")
async def ingest_document(file: UploadFile = File(...)):
    pool = await get_pool()
    raw = await file.read()
    text = extract_text(file.filename, raw)
    chunks = chunk_text(text)

    async with pool.acquire() as conn:
        document_id = await conn.fetchval(
            "INSERT INTO documents (filename, status) VALUES ($1, 'processing') RETURNING id",
            file.filename,
        )

        for idx, chunk in enumerate(chunks):
            vector_id = str(uuid4())
            embedding = embed_text(chunk)

            # --- SPOT 2: replaces the old unconditional collection.add(...) call ---
            if VECTOR_BACKEND == "weaviate":
                weaviate_collection.data.insert(
                    properties={"content": chunk, "documentId": str(document_id), "chunkIndex": idx},
                    vector=embedding,
                )
            else:
                collection.add(
                    ids=[vector_id],
                    embeddings=[embedding],
                    documents=[chunk],
                    metadatas=[{"document_id": str(document_id), "chunk_index": idx}],
                )
            # --- end SPOT 2 ---

            await conn.execute(
                "INSERT INTO chunks (document_id, chunk_index, content, vector_id) VALUES ($1, $2, $3, $4)",
                document_id, idx, chunk, vector_id,
            )

        await conn.execute("UPDATE documents SET status = 'ready' WHERE id = $1", document_id)

    return {"document_id": str(document_id), "chunks_created": len(chunks), "backend": VECTOR_BACKEND}


# --- TODO (Day 1 hands-on) ---
# - Handle re-ingestion of an updated document (delete old chunks/vectors first)
# - Handle delete: DELETE /api/v1/documents/{id} should remove rows AND vectors from Chroma/Weaviate
# - Consider semantic chunking (split on headings/paragraphs) instead of fixed-size —
#   good talking point on chunking trade-offs either way