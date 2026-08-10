# SABRE AI Assistant Platform — 4-Day Build Plan
### Nomura SABRE, DevOps Server Admin (AI & Analytics / SABRE, OPS Powai) — Interview: Monday, Aug 10, 2026

---

## 0. Read this first — what the JD actually asks for

The corporate title says **"DevOps Server Admin,"** but line-by-line, the JD is **not** a pure infra role:

| Category | Weight in JD |
|---|---|
| Python microservices, RAG, vector DB, chat UX, API design, auth | **Required** — 5 of 5 responsibility groups, both technical-skill bullets |
| DevOps practices, CI/CD pipelines | **Preferred**, not required (1 bullet, under "Preferred Qualifications") |

So the plan below deliberately spends most of your *new* hours on the application layer (RAG mechanics, a named vector DB, auth, a real chat UI, concurrent-user tuning) and treats DevOps as the amplifier you already own — not the thing you need 40 hours to learn.

**SABRE** = *Strategic, Analytics and Business Re-engineering* — confirmed via Nomura's own careers page for a related SABRE role. It's a business-facing team inside Operations that rapid-prototypes data/AI solutions and re-engineers processes — not a central platform-engineering org. Translation: they'll care as much about "can you ship something a business team can use" as "can you run Kubernetes." Keep that framing in your answers.

Nomura's own competency framework (from the JD) is: **Culture & Conduct · Client-Centricity & Business Acumen · Strategy & Innovation · Leadership & Collaboration · Communication & Influence · Execution & Delivery.** Your behavioral answers (Section 8) are mapped to these directly.

---

## 1. Your existing arsenal — lead with this

You are not starting from zero. Before you write a line of new code, know how to sell what you've already built:

| Existing project | Maps to JD requirement |
|---|---|
| **TaskFlow** — Terraform + multi-region EKS + ArgoCD GitOps + DR (RPO≈0/RTO~5min) | "Ensure platform scalability and reliability for enterprise-wide deployment"; DevOps/CI-CD preferred qualification |
| **Bedrock MLOps** — FastAPI `/chat` + `/health`, LangGraph agent, IRSA, ALB Ingress, GitHub Actions CI/CD, Trivy, observability in progress | "Python-based microservices," "API endpoints," "RAG architecture," CI/CD |
| **Financial chatbot** — WebSocket API Gateway + Lambda + Bedrock Claude, collects user data conversationally | "Chat interface functionality," "conversational AI systems" |

The new project below exists to close the **specific, named gaps**: a vector DB from their exact list (Pinecone/Weaviate/ChromaDB), real auth, a real web chat UI, and proof you've tuned something for concurrent users. Everything else, you reuse.

---

## 2. The project: "Argus"

A RAG-based internal document assistant — upload docs, ask questions in a web chat UI, get grounded answers with citations, multi-user, authenticated, deployed on EKS with CI/CD and observability. It's a deliberately scaled-down mirror of what the JD describes as the team's own platform — that's your interview narrative: *"I built a smaller version of what I understand your platform does, specifically to prepare for this conversation."*

You can rename it — the name doesn't matter, the traceability does.

### Architecture

```mermaid
flowchart LR
    U[Browser: React chat UI] -- WebSocket/HTTPS --> GW[chat-svc :: FastAPI]
    U -- HTTPS --> AUTH[auth-svc :: FastAPI]
    GW --> RET[retrieval-svc :: FastAPI]
    RET --> VDB[(ChromaDB\n+ Weaviate on EKS, stretch)]
    ING[ingestion-svc :: FastAPI] --> VDB
    ING --> PG[(PostgreSQL\ndocs / chunks / sessions / messages)]
    GW --> PG
    AUTH --> PG
    GW --> LLM[Bedrock Claude]
    ING --> EMB[Bedrock Titan Embed v2]
    RET --> EMB
    subgraph Observability
      PROM[Prometheus/Grafana]
    end
    GW -.metrics.-> PROM
    RET -.metrics.-> PROM
```

Four Python microservices (`auth-svc`, `ingestion-svc`, `retrieval-svc`, `chat-svc`), one Postgres for structured/session data, one vector store for embeddings, one thin web UI.

---

## 3. JD requirement → where it's proven

| JD line | Covered by |
|---|---|
| Python-based microservices | 4 FastAPI services, independently deployable |
| API endpoints for enterprise integration | REST, OpenAPI/Swagger, `/api/v1` versioning, Pydantic schemas |
| RAG architecture | chunk → embed → store → retrieve → augment → generate, end to end |
| Vector DB (Pinecone/Weaviate/ChromaDB) | ChromaDB (primary, containerized) + Weaviate on EKS (Day 3) + Pinecone adapter (stretch) |
| Chat interface & UX | React chat UI, streaming, session history, citations shown inline |
| DB maintenance for KB storage | Postgres schema with indexes/FKs, backup note in runbook |
| User authentication & security protocols | JWT, bcrypt, protected routes, rate limiting |
| Performance for multiple concurrent users | async services, Locust load test, one measured optimization |
| Web-based interface for end-user access | deployed chat UI behind Ingress |
| Troubleshooting / documentation | README, architecture doc, runbook |
| DevOps practices & CI/CD (preferred) | Docker, K8s manifests, GitHub Actions → ECR → ArgoCD, Prometheus/Grafana |

Nothing in the JD is left uncovered. If Day 3's stretch goals slip, the "preferred" row is what already exists from TaskFlow/Bedrock MLOps — say so honestly rather than rebuilding it.

---

## 4. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language/framework | Python 3.11, FastAPI, async everywhere | Matches JD exactly; async matters for the concurrency story |
| LLM | Bedrock Claude (Sonnet or Haiku) | You already have Bedrock access/IAM from Bedrock MLOps — reuse, don't reprovision |
| Embeddings | Bedrock Titan Embed v2 | Same account, no new integration to debug |
| Vector DB (primary) | **ChromaDB**, run as a Docker server (not embedded) | Fastest real setup — a single `pip install`/container gets you to working RAG same day, still a genuine "hands-on" story |
| Vector DB (stretch, Day 3) | **Weaviate** via Helm on your existing EKS | Self-hosted + K8s ops in one motion; hybrid (BM25+vector) search is a strong talking point |
| Vector DB (stretch, if time) | **Pinecone** (free tier — no card, 2GB, doesn't expire while active, ≈₹0) | Prove your retrieval layer is swappable via an interface — architecture-flexibility story |
| Relational DB | PostgreSQL | You already run CloudNativePG-style Postgres from TaskFlow |
| Auth | JWT (access + refresh), bcrypt | Standard, defensible, fast to build |
| Frontend | React + Vite, minimal components | Modern enough for "web development proficiency," small enough to finish in one day |
| Containers/orchestration | Docker, EKS (reuse TaskFlow cluster), Helm | Zero new infra to stand up |
| CI/CD | GitHub Actions → ECR → ArgoCD sync | Copy your Bedrock MLOps pipeline, adapt |
| Observability | kube-prometheus-stack (already installed) + `prometheus_client` custom metrics | Reuse, add RAG-specific metrics |
| Load testing | Locust | Fast to script, gives you real p50/p95/p99 numbers to quote |

A note on cost: reusing the TaskFlow EKS cluster means near-zero incremental AWS spend. Bedrock is pay-per-token — a few hundred test calls over 3 days should stay under ₹500–₹1,000. Everything else (ChromaDB, Weaviate self-hosted, Postgres) runs on infrastructure you already pay for. Pinecone and Weaviate Cloud entry tiers (≈₹4,750/mo and ≈₹2,375/mo respectively, at today's ≈₹95/$1) are mentioned only for comparison — you won't be billed for them if you stay on free/self-hosted tiers.

---

## 5. Calendar mapping

It's **Thursday 8 PM** right now. Monday is interview day, not a build day — so the honest math is **3 full 10-hour days**, not 4:

| Day | Date | Hours | Focus |
|---|---|---|---|
| Day 0 (optional) | Tonight, Thu Aug 6 | ~1.5–2 hrs | Remove friction only — no learning yet |
| Day 1 | Fri Aug 7 | 10 hrs | Core RAG microservices |
| Day 2 | Sat Aug 8 | 10 hrs | Auth, API polish, chat UI |
| Day 3 | Sun Aug 9 | 10 hrs | DevOps layer, performance, docs |
| Day 4 | Mon Aug 10 (AM only) | ~2–3 hrs | Review, mock Q&A, rest — **not** a build day |

Treat the hour labels below as a sequence, not a stopwatch — if a block runs long, borrow from a later one rather than skipping sleep.

---

## 6. Day 0 — Tonight (optional, ~1.5–2 hrs)

Pure setup, zero learning-bearing work, so Day 1 starts at full speed:

- Confirm Bedrock model access (Claude + Titan Embed v2) in your AWS account/region
- `docker pull chromadb/chroma`, confirm it runs locally
- Create a free Pinecone account (email only, no card) — just so it's not blocking you Day 3
- `git init` the repo, scaffold the folder tree (Section 9), commit empty skeleton
- Confirm your TaskFlow EKS cluster is still up (`kubectl get nodes`) or note if you need to recreate it — if recreating, do it tonight, not Sunday

---

## 7. Day 1 — Friday Aug 7: Core RAG (10 hrs)

**Goal by end of day:** curl/Swagger a question, get a grounded answer with citations, end to end, locally via docker-compose.

- **Hr 1** — `docker-compose up postgres chromadb`, run `db/init.sql`, sanity-check both are reachable.
- **Hr 2–3** — `ingestion-svc`: file upload endpoint → text extraction (PDF/txt) → chunking. Start with fixed-size + overlap (e.g. 500 tokens, 50 overlap); note *why* as a talking point — too small loses context, too large dilutes retrieval precision and wastes tokens. Call Titan Embed v2, upsert into ChromaDB with metadata (`document_id`, `chunk_index`), write a `chunks` row per chunk.
- **Hr 4–5** — `retrieval-svc`: `/search` — embed the query, top-k similarity search against ChromaDB, return chunks + scores. If time allows, add simple keyword-boost re-ranking (talking point: pure cosine similarity vs. hybrid).
- **Hr 6–7** — `chat-svc`: `/chat` — take `{session_id, message}`, call retrieval-svc, build a prompt that forces citation of chunk IDs, call Bedrock Claude, stream the response (SSE is fine for today; WebSocket comes Day 2), persist both messages to `messages`.
- **Hr 8** — `/health` on every service; structured JSON logging (one log line per request with latency).
- **Hr 9** — End-to-end test: ingest 3–5 real documents (your resume, an AWS whitepaper, a sample policy doc), ask 10 questions via Swagger UI, verify citations are correct, and **deliberately test what happens when nothing relevant exists** — it should say so, not hallucinate.
- **Hr 10** — Commit with clean messages; write down 5 rough talking points while they're fresh (chunking trade-off, why grounded-refusal matters in a banking context, embedding choice).

---

## 8. Day 2 — Saturday Aug 8: Auth, API polish, chat UI (10 hrs)

**Goal by end of day:** a real person can log in, chat, see history, and a second person's session stays isolated.

- **Hr 1–2** — `auth-svc`: `/register`, `/login` (bcrypt hash + verify), JWT issue (short-lived access + refresh), `/me`.
- **Hr 3** — JWT-verification dependency, applied to `chat-svc` and `ingestion-svc` routes. Add a coarse `role` field (`user`/`admin`) on the user — enterprise auth in the JD implies more than "logged in or not."
- **Hr 4** — Basic rate limiting on `/chat` (slowapi or a simple in-memory token bucket) — this is your first concrete answer to "optimize platform performance for multiple concurrent users."
- **Hr 5** — API polish: Pydantic request/response models everywhere, consistent error envelope, real HTTP status codes, `/api/v1` prefix.
- **Hr 6–8** — Frontend (React + Vite): login screen, chat window, streaming message display, session sidebar, citations rendered under each answer. Keep components minimal — Login, ChatWindow, MessageList, SessionSidebar. Function over polish.
- **Hr 9** — Move `chat-svc` from SSE to WebSocket for streaming (same mental model as your financial-chatbot's WebSocket API Gateway pattern, just direct FastAPI here — be ready to explain both approaches and when you'd pick API Gateway+Lambda over a direct WS server).
- **Hr 10** — Two-browser test (normal + incognito) as two different users — confirm chat history doesn't leak across sessions. Commit.

---

## 9. Day 3 — Sunday Aug 9: DevOps, performance, docs (10 hrs)

**Goal by end of day:** deployed on EKS, one load-tested and fixed bottleneck, documented.

- **Hr 1–2** — Harden Dockerfiles (multi-stage, non-root, slim base — this is fast for you). Confirm full stack boots clean from `docker-compose up` alone.
- **Hr 3–4** — K8s manifests/Helm values; deploy to your existing TaskFlow EKS cluster via ArgoCD (new `Application` pointing at this repo's `k8s/` path). Secrets via AWS Secrets Manager, same pattern as before. **Skip re-doing ACM/Route53/custom domain** — that's a proven skill, not a gap; port-forward or a plain ALB is enough to demo.
- **Hr 5** — Deploy Weaviate via its Helm chart into a separate namespace on the same cluster. This is your second hands-on named vector DB, and pairs K8s ops with the exact JD line about vector databases.
- **Hr 6** — GitHub Actions: adapt your Bedrock MLOps pipeline (lint/test → Docker build → ECR push → ArgoCD sync/`kubectl apply` → smoke test). Keep the Trivy scan step.
- **Hr 7** — Observability: point at your existing kube-prometheus-stack; add custom metrics via `prometheus_client` — retrieval latency histogram, chat latency, a rough token-cost gauge. One Grafana panel is enough to show, not a full dashboard.
- **Hr 8** — Load test with Locust: ramp 20 → 50 → 100 concurrent simulated chat users against `/chat`. Record p50/p95/p99 and error rate. Identify the actual bottleneck (likely: Bedrock call latency, or Postgres connection exhaustion under async load).
- **Hr 9** — Apply **one** concrete fix for the bottleneck you found (connection pooling, `aioboto3` for non-blocking Bedrock calls, caching repeated queries, or an HPA on `chat-svc`). Re-run Locust, record the before/after numbers — this single before/after is your strongest performance story, so don't skip re-measuring.
- **Hr 10** — README, architecture doc (export the Mermaid diagram), a short runbook (deploy, rollback, "if X breaks, check Y"). If time remains: the Pinecone adapter — a `VectorStore` interface with Chroma/Weaviate/Pinecone implementations, swapped via env var. Even a partial version proves the design intent.

---

## 10. Day 4 — Monday Aug 10, morning only: Review (~2–3 hrs, not a build day)

1. Re-read the JD line by line against Section 3's table — for every bullet, be ready to say in one sentence how you demonstrated it.
2. Say 5–6 STAR stories out loud, timed to 60–90 seconds each — pull from **all four** projects (TaskFlow, Bedrock MLOps, financial chatbot, Argus), not just the new one. See Section 12.
3. One pass through Section 11's mock questions — out loud, not just in your head.
4. Prepare your 3–4 questions for them (Section 13).
5. Logistics: resume ready, interview link/location tested, quiet space, water, log in or arrive 10 minutes early.
6. Stop adding new material after this. Rest beats cramming.

---

## 11. Starter scaffold

```
argus/
├── README.md
├── docker-compose.yml
├── .env.example
├── .gitignore
├── db/
│   └── init.sql
├── services/
│   ├── auth-svc/{app/,requirements.txt,Dockerfile}
│   ├── ingestion-svc/{app/,requirements.txt,Dockerfile}
│   ├── retrieval-svc/{app/,requirements.txt,Dockerfile}
│   └── chat-svc/{app/,requirements.txt,Dockerfile}
├── frontend/                # React + Vite
├── k8s/                     # Helm values / manifests — filled Day 3
└── docs/
    ├── ARCHITECTURE.md
    └── RUNBOOK.md
```

### `db/init.sql`

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'user',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename VARCHAR(512) NOT NULL,
    uploaded_by UUID REFERENCES users(id),
    status VARCHAR(50) NOT NULL DEFAULT 'processing',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    vector_id VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    title VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    citations JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_chunks_document ON chunks(document_id);
CREATE INDEX idx_messages_session ON messages(session_id);
CREATE INDEX idx_sessions_user ON chat_sessions(user_id);
```

### `docker-compose.yml`

```yaml
version: "3.9"
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: argus
      POSTGRES_USER: argus
      POSTGRES_PASSWORD: argus_dev_pw
    ports: ["5432:5432"]
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./db/init.sql:/docker-entrypoint-initdb.d/init.sql

  chromadb:
    image: chromadb/chroma:latest
    ports: ["8000:8000"]
    volumes:
      - chromadata:/chroma/chroma

  auth-svc:
    build: ./services/auth-svc
    ports: ["8001:8000"]
    environment:
      - DATABASE_URL=postgresql://argus:argus_dev_pw@postgres:5432/argus
      - JWT_SECRET=${JWT_SECRET}
    depends_on: [postgres]

  ingestion-svc:
    build: ./services/ingestion-svc
    ports: ["8002:8000"]
    environment:
      - DATABASE_URL=postgresql://argus:argus_dev_pw@postgres:5432/argus
      - CHROMA_HOST=chromadb
      - AWS_REGION=ap-south-1
    depends_on: [postgres, chromadb]

  retrieval-svc:
    build: ./services/retrieval-svc
    ports: ["8003:8000"]
    environment:
      - CHROMA_HOST=chromadb
      - AWS_REGION=ap-south-1
    depends_on: [chromadb]

  chat-svc:
    build: ./services/chat-svc
    ports: ["8004:8000"]
    environment:
      - DATABASE_URL=postgresql://argus:argus_dev_pw@postgres:5432/argus
      - RETRIEVAL_URL=http://retrieval-svc:8000
      - AWS_REGION=ap-south-1
    depends_on: [postgres, retrieval-svc]

  web-ui:
    build: ./frontend
    ports: ["3000:3000"]
    environment:
      - VITE_API_URL=http://localhost:8004
      - VITE_AUTH_URL=http://localhost:8001

volumes:
  pgdata:
  chromadata:
```

Each `services/*/requirements.txt` starts minimal: `fastapi`, `uvicorn[standard]`, `pydantic`, `asyncpg` or `sqlalchemy[asyncio]`, `boto3`/`aioboto3`, `chromadb` (for the services that talk to it), `python-jose` + `passlib[bcrypt]` (auth-svc only).

---

## 12. STAR stories to have ready (60–90 sec each)

Map to Nomura's stated competencies:

| Competency | Story to use |
|---|---|
| Strategy & Innovation / Decision Making | TaskFlow's DR design trade-off (RPO≈0 / RTO~5min) — a concrete, quantified decision under constraints |
| Execution & Delivery / Adaptability | This very week — a 3-day sprint against a fixed interview deadline, re-prioritizing daily |
| Client-Centricity / Analytical Thinking | Financial chatbot — translating "collect a user's financial details conversationally" into an architecture |
| Communication & Influence | Explaining a CI/CD or GitOps decision to a less infra-savvy stakeholder on Bedrock MLOps |
| Leadership & Collaboration | Your mentoring work (Python/Django mentee) — supporting someone else's growth |
| Culture & Conduct / Self-Awareness | A time you changed your own technical approach after realizing a better one existed |

---

## 13. Mock interview bank

**Technical / RAG:**
1. Walk me through Argus end to end — a raw PDF to a cited answer.
2. Why ChromaDB for the core build, and when would you reach for Pinecone or Weaviate instead?
3. How do you choose chunk size and overlap? What breaks at each extreme?
4. How do you stop the model from hallucinating when retrieval returns nothing useful?
5. How do you keep the vector index in sync when a source document changes or is deleted?
6. How would you evaluate whether your RAG answers are actually correct, not just fluent?

**Auth / API / performance:**
7. Why JWT over session cookies here? How do you handle expiry and refresh?
8. Your load test — what broke first at scale, and what did you change?
9. Where does `async` actually matter in this system, concretely?
10. How would you extend this to per-user document access permissions across business lines?

**System design (rehearse this explicitly — near-certain to come up):**
11. "Design an internal AI assistant used by ~2,000 employees across several business lines, with different document-access permissions per user."

**Platform / enterprise:**
12. How do you handle PII in documents ingested into a vector store, inside a bank?
13. What would page you at 3 AM in production, and why those metrics specifically?
14. If told to swap Bedrock Claude for a self-hosted open model, what changes and what doesn't?

---

## 14. Questions worth asking them

- Which of Pinecone, Weaviate, or ChromaDB are you running today, and at roughly what scale?
- The team overview mentions agentic AI — how far along is that relative to the RAG/chat work?
- What does ownership/on-call look like for a platform multiple business lines depend on?
- What's the single biggest technical pain point on the platform right now?

---

## 15. If you fall behind — what to cut, in order

1. Pinecone adapter spike (Day 3, last item) — mention it as a documented design intent instead.
2. Weaviate-on-K8s hands-on — fall back to "read the docs + can compare firsthand-vs-documented" instead of deployed.
3. Full ArgoCD GitOps redeploy — `kubectl apply` a static manifest and describe the GitOps path verbally; you've already proven GitOps on TaskFlow.
4. Multi-stage Locust ramp — one quick run at a single concurrency level beats none.
5. Frontend polish — it only needs to function, not look production-grade.

**Never cut:** the four services talking to each other end to end, basic auth, Section 10's review morning, and rehearsing the STAR stories out loud. A well-articulated 80%-built system beats a rushed 100%-built one nobody rehearsed explaining.

---

## 16. One-page cheat sheet (re-read this Monday morning)

- **One-liner:** "Argus — a RAG-based internal document assistant with auth, a chat UI, and multi-vector-DB support, built to mirror what I understand SABRE's AI Assistant platform does."
- **Stack:** FastAPI (4 services) · Bedrock Claude + Titan Embed · ChromaDB (+Weaviate on EKS) · Postgres · JWT auth · React · EKS/ArgoCD/GitHub Actions · Prometheus/Grafana.
- **Your edge:** DR-grade multi-region infra (TaskFlow) most candidates won't have — but lead with the application layer first, since that's ~80% of the JD.
- **Numbers to have ready:** your Locust p95 before/after the fix; your chunk size/overlap and why.
- **SABRE = Strategic, Analytics and Business Re-engineering** — rapid prototyping + process re-engineering inside Ops, not a central platform team.
