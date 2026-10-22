# 0003. Emulate AWS locally with moto, the Lambda RIE and Ollama (not LocalStack)

- Status: accepted
- Date: 2026-10-22

## Context

Days 1–7 of the plan had to run **without an AWS account and at $0**, so that anyone can clone the repo and run everything. The system needs three AWS pieces locally:

| AWS service | Used for |
|---|---|
| Amazon S3 | Model artifacts (`related.json`, `popular.json`, `search_index.json`) |
| AWS Lambda (+ API Gateway) | Running the FastAPI app as a function |
| Amazon Bedrock | Embeddings for `/search` |

The usual all-in-one emulator is LocalStack. Since March 2026 it ships as a single image that requires an account and an auth token, with a free plan limited to non-commercial use.

## Decision

Use one small, free tool per service, all started with `docker compose` (`docker-compose.yml`):

| AWS | Local replacement | Why |
|---|---|---|
| S3 | **moto** server (`motoserver/moto`) on `:5000` | Free, no sign-up. It is the same library the tests use (`moto.mock_aws`), so tests and local runs share one mental model |
| Lambda | **AWS Lambda Python base image** (`public.ecr.aws/lambda/python:3.12`), which includes the Runtime Interface Emulator, on `:9000` | Official AWS image running the **same zip** that is deployed |
| API Gateway | `src/scripts/invoke_lambda.py` builds the HTTP API v2 event | The event contract is explicit and testable (`tests/test_lambda_handler.py`) |
| Bedrock | **Ollama** + `nomic-embed-text` on `:11434` | Local embeddings at $0, behind LangChain's `Embeddings` interface |

The code switches between local and AWS **by configuration only**: `S3_ENDPOINT_URL` (`src/app/infrastructure/aws.py`) and `EMBEDDINGS_PROVIDER` (`src/app/infrastructure/embeddings.py`).

AWS SAM CLI (`sam local`) was used in an early draft and replaced by Terraform + the RIE container, so that one tool (Terraform) owns the infrastructure.

## Consequences

- **Positive:** $0, no accounts, everything starts with `make up-ai` / `make lambda-up`. The Lambda package tested locally is byte-for-byte the one deployed. Tests need none of it (moto runs in memory), so CI stays simple.
- **Negative:**
  - moto keeps data **in memory**: artifacts must be re-uploaded after a restart (`make upload-local`).
  - The RIE serves one invocation at a time and reports misleading numbers (`Init Duration: 0.61 ms`, a fake `Memory Size`), so performance must be measured on AWS.
  - Ollama and Titan produce different vectors, so the search index is rebuilt per environment.
  - API Gateway behavior (throttling, auth) is not emulated.
- **Observed:** the local cold start (~14 s) was inflated by Docker on Windows reading the bind-mounted package. On AWS it was 3.36 s on average (README → Findings).
