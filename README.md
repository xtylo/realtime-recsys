# Real-Time Recommendation System

**Problem:** E-commerce platforms lose sales because their recommendations do not adapt to what users are doing *right now*.

**Solution:** A real-time recommendation API that updates product suggestions on every user interaction (view, add-to-cart, purchase) within the same session. It is built with Python 3, FastAPI, AWS Lambda, S3 and LangChain.

**Impact (design targets):** Sized for **1M daily users** (~2,000 req/s at peak) with **p99 latency < 200 ms**. Business impact is estimated offline by replaying real e-commerce sessions and comparing against a popularity baseline. Measured results are published in [Target metrics](#target-metrics) as each phase is completed.

**Tech stack:** Python 3.12 · FastAPI · AWS Lambda · Amazon S3 · API Gateway · LangChain · Amazon Bedrock · Terraform · Docker · k6

**New technologies to learn:** Python 3, FastAPI, AWS Lambda, LangChain, Terraform

> 🚧 Work in progress: phases 1–3 are complete and verified locally; AWS deployment and load testing are next. Step-by-step plan: [`docs/PLAN.md`](docs/PLAN.md). Measured results: [Findings](#findings).

## Phased plan

| Phase | Scope | Plan days | Status |
|---|---|---|---|
| **1. Design & data** | Architecture, dataset (REES46), baseline recommender artifacts | Days 0–2 | ✅ Done |
| **2. Backend: FastAPI + AWS Lambda** | Session-aware API, S3 model loading, Lambda packaging | Days 3–5 | ✅ Done (local Lambda emulator) |
| **3. LangChain integration** | Natural-language product search with embeddings | Day 6 | ✅ Done (Ollama embeddings) |
| **4. Deploy, latency & load testing** | CI, Terraform deployment, k6 load tests, offline uplift estimate | Days 7–8 | 🟡 Local load tests done; AWS pending |

## Overview

The system receives user interaction events in real time, keeps a short-lived view of the current shopping session and answers with personalized product recommendations. It is exposed as a REST API built with FastAPI. The same code runs locally with uvicorn and on AWS Lambda behind API Gateway.

Recommendations come from a fast, explainable model (session-weighted item co-occurrence with a popularity fallback) that is pre-computed offline and loaded from S3 at cold start. LangChain is used where language models add value without hurting latency: semantic product search over embeddings. The LLM stays out of the hot path of every recommendation request.

The whole environment runs locally for $0 using emulators: moto for S3, the AWS Lambda Runtime Interface Emulator and Ollama for embeddings. A single Terraform apply deploys it to real AWS.

## Architecture

```mermaid
flowchart LR
    U[User actions<br/>e-commerce app] -->|HTTPS| GW[API Gateway<br/>HTTP API]
    GW --> L[AWS Lambda<br/>FastAPI + Mangum]
    L -->|cold start: load model| S3[(Amazon S3<br/>model artifacts)]
    L -->|/search: embed query| BR[Amazon Bedrock<br/>Titan embeddings]
    subgraph Offline training
        D[REES46 events] --> T[src/training<br/>pandas + LangChain]
    end
    T -->|upload_model.py| S3
```

- **User actions**: events (`view`, `cart`, `purchase`) sent by the e-commerce front end.
- **API Gateway (HTTP API)**: public HTTPS endpoint; forwards every route to the Lambda function.
- **AWS Lambda (FastAPI + Mangum)**: validates requests, updates the session and ranks candidates. Mangum adapts API Gateway events to FastAPI.
- **Amazon S3**: stores model artifacts (popular items, item co-occurrence, search index) and the Lambda package.
- **LangChain + Bedrock**: embeddings for natural-language product search.
- **Offline training** (`src/training`): builds the artifacts from historical events.

Locally, the same boxes are replaced by moto (S3), the Lambda Runtime Interface Emulator (Lambda) and Ollama (Bedrock), all started with `docker compose`.

## Repository structure

```
.
├── .devcontainer/            # Optional VS Code Dev Container (Python 3.12, uv, local S3)
├── docker-compose.yml        # Local cloud simulation: S3 (moto), Ollama, Lambda emulator, k6
├── loadtest/
│   └── k6.js                 # Load test (smoke and 1,000-VU profiles)
├── src/
│   ├── app/                  # FastAPI application (domain + infrastructure)
│   ├── lambda/
│   │   └── handler.py        # AWS Lambda entry point (Mangum)
│   ├── training/             # Offline jobs that build the model artifacts
│   ├── scripts/              # build_lambda, invoke_lambda, upload_model, local-env.ps1
│   └── infra/
│       └── terraform/        # API Gateway, Lambda, S3, IAM, CloudWatch
├── tests/                    # pytest unit and integration tests
└── docs/
    ├── PLAN.md               # Day-by-day implementation plan
    └── adr/                  # Architecture Decision Records
```

## Local environment (cloud simulation)

Prerequisites: [uv](https://docs.astral.sh/uv/) and Docker Desktop. **No AWS account is needed.**

```powershell
# 1. Install dependencies and run the tests
uv sync
uv run pytest -v

# 2. Run the API (Swagger UI at http://127.0.0.1:8000/docs)
uv run uvicorn app.main:app --reload

# 3. Start the local AWS services
docker compose up -d                       # S3 emulator (moto) on :5000
docker compose --profile ai up -d          # + Ollama embeddings on :11434

# 4. Run the code as a real Lambda function (Runtime Interface Emulator on :9000)
uv run python src/scripts/build_lambda.py
docker compose --profile lambda up -d lambda
uv run python src/scripts/invoke_lambda.py GET /health
```

On the host, `. .\src\scripts\local-env.ps1` points the app to the local services. If you use the Dev Container, they are configured automatically.

| Real AWS | Local emulator |
|---|---|
| Amazon S3 | [moto](https://github.com/getmoto/moto) server (`s3` service) |
| AWS Lambda | AWS Lambda Python base image with the Runtime Interface Emulator (`lambda` service) |
| API Gateway | `src/scripts/invoke_lambda.py` builds the API Gateway v2 event |
| Amazon Bedrock | [Ollama](https://ollama.com) + `nomic-embed-text` (`ollama` service) |

**Option B – Dev Container:** open the folder in VS Code and run **Dev Containers: Reopen in Container**. You get Python 3.12 and uv with the local S3 service already wired. Start Ollama from a host terminal when you need it (`docker compose --profile ai up -d`).

## Cloud deployment

The infrastructure is defined with Terraform in [`src/infra/terraform`](src/infra/terraform). It creates the API Gateway HTTP API, the Lambda function, the S3 bucket, a least-privilege IAM role and CloudWatch logs.

```powershell
uv run python src/scripts/build_lambda.py           # build/lambda.zip

cd src/infra/terraform
Copy-Item terraform.tfvars.example terraform.tfvars  # set artifacts_bucket_name
terraform init
terraform apply

cd ../../..
uv run python src/scripts/upload_model.py --bucket <artifacts_bucket output>
curl.exe "$(terraform -chdir=src/infra/terraform output -raw api_url)health"
```

**Production checklist**
- [ ] AWS budget alert configured before the first deployment
- [ ] `terraform plan` reviewed: only the expected resources are created
- [ ] Model artifacts uploaded before the first request (the Lambda loads them at cold start)
- [ ] Smoke test of `/health`, `/events` and `/recommendations` against the public URL
- [ ] CloudWatch logs and `Init Duration` (cold start) reviewed
- [ ] `terraform destroy` when finished, to avoid charges

## Load testing

[k6](https://grafana.com/docs/k6/latest/) simulates shoppers. Each virtual user sends an event, asks for recommendations and waits 1 second, so ~1,000 virtual users produce ~2,000 requests/s.

| Profile | Shape | Use |
|---|---|---|
| `smoke` (default) | 5 users for 30 s | Local sanity check |
| `load` | 0 → 1,000 users in 5 min, hold 10 min, ramp down 1 min | Against AWS |

```powershell
docker compose --profile loadtest run --rm k6                         # smoke test against the local API
docker compose --profile loadtest run --rm -e PROFILE=load -e BASE_URL=<api_url> k6
```

The script fails the run if the error rate is ≥ 0.1% or p99 latency of `/recommendations` is ≥ 200 ms.

> New AWS accounts often have a low Lambda concurrency quota. Check *Service Quotas → AWS Lambda → Concurrent executions* before running the `load` profile.

## Target metrics

| Metric | Target | How it is measured | Local result (laptop) | AWS result |
|---|---|---|---|---|
| Throughput | 2,000 req/s sustained | k6 `load` profile | **~600 req/s** with one uvicorn process (saturated, see [Findings](#findings)) | TBD |
| Latency p95 / p99 (`/recommendations`) | p99 < 200 ms | k6 `http_req_duration{endpoint:recommendations}` | **4.0 ms / 4.7 ms** at low load (5 VUs) | TBD |
| Error rate | < 0.1% | k6 `http_req_failed` + Lambda error metrics | **0%** (0 of 558,084 requests, even when saturated) | TBD |
| Saturation point | Degradation from ~3,500 req/s | Step-up k6 run until latency or errors break the targets | **~600 req/s / ~300 VUs** for a single process | TBD |
| Cold start | Measured and documented | Lambda `Init Duration` | ~14.2 s in the local emulator (inflated, see Findings) | TBD |
| Warm invocation | — | Lambda `Duration` | **2.5–6.3 ms** (local Lambda emulator) | TBD |
| Recommendation quality | Beat the popularity baseline | Offline Recall@10 / NDCG@10 on a temporal split | Not measured yet | — |
| Cost | Measured and documented | Cost per 1M requests (Lambda + API Gateway + S3) | — | TBD |

## Findings

What was measured and learned while building the local foundation (Days 2–7). Environment: Windows laptop, Docker Desktop, Python 3.12.

### 1. Model artifacts (Day 2)
- Built from the first **200,000 events** of REES46 *2019-Oct*: **100** popular products and **27,977** products with co-occurrence neighbors (avg **12.3** related items each; 9,962 reach the cap of 20).
- Raw co-occurrence counts favor products that appear everywhere (popular items show up as "related" to many products). This is popularity bias, and normalization (cosine or lift) is a planned improvement.
- The sample covers only the first hours of October (`nrows` is not a random sample). This is a known temporal bias.

### 2. Recommendation behavior (Day 3)
- Recommendations change on every event. Weights: `purchase` 5 > `cart` 3 > `view` 1, with a 0.8 recency decay.
- Products already seen in the session are **excluded on purpose** (discovery carousel). Repeating the same event strengthens that product's *neighbors*, not the product itself.
- The session keeps only the last 20 events, so a burst of repeated events can push older context out. Collapsing consecutive duplicates is a planned improvement.

### 3. Lambda execution model (Day 5)
| Measurement (local Lambda Runtime Interface Emulator) | Result |
|---|---|
| Cold start (`INIT REPORT durationMs`) | ~14.2 s |
| Warm invocations | 2.5–6.3 ms |
| Session after restarting the function (= new instance) | Lost |

- The 14.2 s cold start is **not representative**: Docker on Windows reads thousands of package files from a bind mount. The RIE's own `REPORT` line also shows a misleading `Init Duration: 0.61 ms` and a fake `Memory Size`. The real number will come from AWS.
- **Mangum runs the FastAPI lifespan on every invocation.** Initialization therefore lives at module level in `src/lambda/handler.py` (once per cold start), with `lifespan="off"`.
- Each Lambda instance has its own memory and serves one request at a time, so in-memory session state is not shared → [ADR 0001](docs/adr/0001-session-state.md) (DynamoDB for production).

### 4. Search with embeddings (Day 6)
- `/search` uses an embeddings model (`nomic-embed-text` via Ollama locally, Titan on Bedrock in AWS) through LangChain's `Embeddings` interface. No generative LLM is called per request → [ADR 0002](docs/adr/0002-llm-out-of-hot-path.md).
- Configuration is per runtime. The local Lambda reads its environment from `docker-compose.yml`, not from the developer's terminal, the same way the real Lambda reads it from Terraform. Changing it requires recreating the container (`--force-recreate`).
- The downloaded index is stored in the OS temp folder (`tempfile.gettempdir()`), which is `/tmp` on Lambda and `%TEMP%` on Windows.

### 5. Load testing (Day 7)
**Smoke test** (k6, 5 VUs, 30 s, single uvicorn process): p95 **3.8 ms**, p99 **4.7 ms** for `/recommendations`, **0%** errors, ~5 req/s. The hot path is in-memory lookups, which supports the design in ADR 0002.

**Stress test** (k6 `load` profile: ramp to 1,000 VUs, hold 10 min; uvicorn and k6 on the same laptop):

| Metric | Result |
|---|---|
| Requests | 558,084 in 16 min (avg **~580 req/s**) |
| Errors | **0%** |
| `/recommendations` p95 / p99 | **2.07 s / 2.55 s** |
| Iteration duration | avg 2.8 s (ideal ~1 s) |

Analysis with **Little's law** (`throughput = concurrency / time per iteration`):
- 1,000 VUs ÷ ~3.4 s per iteration ≈ 290 iterations/s ≈ **~600 req/s**, the capacity of one Python process on this machine.
- Each VU generates ~2 req/s, so saturation starts at ~600 ÷ 2 ≈ **300 VUs**. Beyond that, extra users only add queueing: latency grows, errors do not. k6 uses a closed model, where each VU waits for its response, so load self-throttles.
- Limits come from a single process (the GIL), k6 competing for the same CPU, and Docker Desktop networking.

**Architectural implication:** one uvicorn process scales *vertically* (one queue). Lambda scales *horizontally* (one instance per concurrent request). Required concurrency = req/s × duration ≈ 2,000 × ~0.005 s ≈ **10–20 concurrent Lambda instances** for the 2,000 req/s target, well within default quotas. Adding uvicorn `--workers` would raise local capacity but split the in-memory session, the same problem documented in ADR 0001.

## Tests (unit / integration)

Tests use pytest. Unit tests cover the domain logic. Integration tests call the API through FastAPI's `TestClient`, call the Lambda handler with real API Gateway events, and use moto to mock S3.

```powershell
uv run pytest -v
uv run ruff check .
```

Example: the Lambda handler tested in-process with an API Gateway HTTP API event ([`tests/test_lambda_handler.py`](tests/test_lambda_handler.py)):

```python
def test_health_through_lambda_handler():
    event = invoke_lambda.build_event("GET", "/health")
    response = lambda_handler.handler(event, FakeLambdaContext())
    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"status": "ok"}
```

## Technical challenges

### Real-time recommendations
**Why it is hard:** recommendations must reflect the last click, not yesterday's batch job, and still answer in milliseconds.
**How it is solved:** the expensive work (co-occurrence and popularity) is pre-computed offline. At request time the API only combines the candidates of the session's recent items, weighting each by event type (purchase > cart > view) and by recency. That is cheap dictionary arithmetic.

### Session state on serverless
**Why it is hard:** Lambda instances do not share memory, and they are recycled at any time, so in-memory session state gets lost.
**How it is solved:** the in-memory store is used only to learn the trade-off (documented as an ADR). The production design moves session state to DynamoDB with a TTL.

### Bias in recommendations
**Why it is hard:** recommenders tend to amplify what is already popular (popularity bias), which hides most of the catalog.
**How it is solved:** popularity is only a fallback, and items the user already saw are filtered out. Catalog coverage and diversity are tracked as evaluation metrics next to accuracy.

### Low latency
**Why it is hard:** serverless adds cold starts, and calling an LLM per request would add hundreds of milliseconds and real cost.
**How it is solved:** model artifacts are loaded once per Lambda instance (at module level, reused while warm). The LLM stays out of the recommendation path, and cold starts are measured and tuned (memory size, package size).

## Takeaways

What this project demonstrates (updated as phases are completed):

- Designing a real-time recommendation API with FastAPI and running it unchanged on AWS Lambda.
- Separating offline training from online serving, with model artifacts versioned in S3.
- Integrating LangChain for semantic search while keeping the LLM out of the latency-critical path.
- Infrastructure as code with Terraform (API Gateway, Lambda, S3, IAM, CloudWatch).
- Developing against local AWS emulators at $0, with the same Lambda package used locally and in the cloud.
- Load testing with k6 and measuring latency percentiles, error rate, cold starts and cost.
- Finding a saturation point and explaining it with Little's law, then translating it into Lambda concurrency.

## Learning path

### Python 3 and FastAPI
Python is the standard language for backend services that sit close to data and ML. FastAPI builds typed, fast APIs with request validation and OpenAPI docs generated from type hints.

1. Learn modern Python syntax, type hints and virtual environments (with uv).
2. Follow the official FastAPI tutorial: path and query parameters, request bodies, dependencies.
3. Add validation, error handling and dependency injection to the recommendation API.
4. Test it with pytest and `TestClient`.
5. Run the same app on AWS Lambda through Mangum.

Resources:
- [The Python Tutorial](https://docs.python.org/3/tutorial/)
- [FastAPI tutorial](https://fastapi.tiangolo.com/tutorial/)
- [uv documentation](https://docs.astral.sh/uv/)

### AWS Lambda, LangChain and Terraform
AWS Lambda runs code without managing servers and scales with traffic. LangChain provides building blocks (embeddings, vector stores, retrievers) to integrate AI models. Terraform describes the cloud infrastructure as code.

1. Understand the Lambda execution model: handler, cold and warm starts, memory and timeout.
2. Package and run a Lambda function locally with the Runtime Interface Emulator.
3. Use LangChain embeddings and a vector store for semantic search.
4. Deploy API Gateway, Lambda and S3 with Terraform.
5. Measure performance with k6 and tune memory, package size and cold starts.

Resources:
- [AWS Lambda Developer Guide](https://docs.aws.amazon.com/lambda/latest/dg/welcome.html)
- [LangChain documentation](https://docs.langchain.com/)
- [Terraform: Get Started – AWS](https://developer.hashicorp.com/terraform/tutorials/aws-get-started)
- [k6 documentation](https://grafana.com/docs/k6/latest/)
