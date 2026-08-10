import os
import json
import logging
import boto3
import chromadb
from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten to your actual ALB hostname before anything resembling production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("retrieval-svc")

app = FastAPI(title="retrieval-svc", version="0.1.0")

CHROMA_HOST = os.environ.get("CHROMA_HOST", "chromadb")
CHROMA_PORT = int(os.environ.get("CHROMA_PORT", "8000"))
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
EMBED_MODEL_ID = os.environ.get("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "argus_chunks")

bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)
chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
collection = chroma_client.get_or_create_collection(COLLECTION_NAME)


def embed_text(text: str) -> list[float]:
    body = json.dumps({"inputText": text})
    resp = bedrock.invoke_model(modelId=EMBED_MODEL_ID, body=body)
    result = json.loads(resp["body"].read())
    return result["embedding"]


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/v1/search")
async def search(req: SearchRequest):
    query_embedding = embed_text(req.query)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=req.top_k,
    )

    hits = []
    ids = results.get("ids", [[]])[0]
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    for i in range(len(ids)):
        hits.append({
            "chunk_id": ids[i],
            "content": docs[i],
            "document_id": (metas[i] or {}).get("document_id"),
            "score": dists[i],
        })

    return {"results": hits}


# --- TODO (Day 1 hands-on) ---
# - Tune top_k / add a simple re-rank pass (e.g. boost chunks containing exact query keywords)
# - Add a /api/v1/search/hybrid endpoint once you deploy Weaviate (Day 3 stretch) to compare
#   pure-vector vs hybrid BM25+vector results side by side — good interview demo material
