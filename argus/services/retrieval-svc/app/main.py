import os
import json
import logging
import time
import boto3
import chromadb
import weaviate
from weaviate.classes.query import HybridFusion
from fastapi import FastAPI
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, make_asgi_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("retrieval-svc")

app = FastAPI(title="retrieval-svc", version="0.2.0")

SERVICE_NAME = "chat-svc"  # change per service: "auth-svc", "retrieval-svc", "ingestion-svc"

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

VECTOR_BACKEND = os.environ.get("VECTOR_BACKEND", "chroma")  # "chroma" or "weaviate"

CHROMA_HOST = os.environ.get("CHROMA_HOST", "chromadb")
CHROMA_PORT = int(os.environ.get("CHROMA_PORT", "8000"))

WEAVIATE_HOST = os.environ.get("WEAVIATE_HTTP_HOST", "weaviate")
WEAVIATE_PORT = int(os.environ.get("WEAVIATE_HTTP_PORT", "8080"))
WEAVIATE_GRPC_PORT = int(os.environ.get("WEAVIATE_GRPC_PORT_NUM", "50051"))
HYBRID_ALPHA = float(os.environ.get("HYBRID_ALPHA", "0.75"))  # 1.0 = pure vector, 0.0 = pure BM25

AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
EMBED_MODEL_ID = os.environ.get("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "argus_chunks")

bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)

chroma_client = None
weaviate_client = None

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


def embed_text(text: str) -> list[float]:
    body = json.dumps({"inputText": text})
    resp = bedrock.invoke_model(modelId=EMBED_MODEL_ID, body=body)
    return json.loads(resp["body"].read())["embedding"]


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


@app.get("/health")
async def health():
    return {"status": "ok", "backend": VECTOR_BACKEND}


@app.post("/api/v1/search")
async def search(req: SearchRequest):
    query_embedding = embed_text(req.query)

    if VECTOR_BACKEND == "chroma":
        results = collection.query(query_embeddings=[query_embedding], n_results=req.top_k)
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]
        hits = [
            {"chunk_id": ids[i], "content": docs[i],
             "document_id": (metas[i] or {}).get("document_id"), "score": dists[i]}
            for i in range(len(ids))
        ]

    elif VECTOR_BACKEND == "weaviate":
        response = weaviate_collection.query.hybrid(
            query=req.query,
            vector=query_embedding,
            alpha=HYBRID_ALPHA,
            fusion_type=HybridFusion.RELATIVE_SCORE,
            limit=req.top_k,
        )
        hits = [
            {"chunk_id": str(obj.uuid), "content": obj.properties.get("content"),
             "document_id": obj.properties.get("documentId"), "score": obj.metadata.score}
            for obj in response.objects
        ]

    return {"results": hits, "backend": VECTOR_BACKEND, "alpha": HYBRID_ALPHA if VECTOR_BACKEND == "weaviate" else None}

