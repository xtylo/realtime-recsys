# Shortcuts for the common tasks. Run `make` (or `make help`) to list them.
# Works on Linux, macOS, WSL, Git Bash and the Dev Container.
# Every target is a thin wrapper: the full command is shown in README.md / docs/PLAN.md.

SHELL := bash
.DEFAULT_GOAL := help

TF                  := terraform -chdir=src/infra/terraform
BASE_URL            ?= http://host.docker.internal:8000
EMBEDDINGS_PROVIDER ?= ollama

.PHONY: help install test lint check run run-public artifacts index up up-ai down \
        upload-local lambda-build lambda-up lambda-logs smoke load \
        openapi aws-guard deploy upload-aws api-url destroy clean

help: ## List the available targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# --- Development --------------------------------------------------------------
install: ## Install dependencies into .venv (uv sync)
	uv sync

test: ## Run the test suite
	uv run pytest -v

lint: ## Lint with ruff
	uv run ruff check .

check: lint test ## Lint + tests (what CI runs)

run: ## Run the API with auto-reload: http://127.0.0.1:8000/docs
	uv run uvicorn app.main:app --reload

run-public: ## Run the API on 0.0.0.0:8000 (reachable from the k6 container)
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

openapi: ## Export the API contract to docs/openapi.json
	uv run python -c "import json; from app.main import app; print(json.dumps(app.openapi(), indent=2))" > docs/openapi.json

# --- Offline training -----------------------------------------------------------
artifacts: ## Build popular.json + related.json from data/raw/2019-Oct.csv
	uv run python -m training.build_artifacts

index: ## Build the search index (EMBEDDINGS_PROVIDER=ollama|bedrock)
	EMBEDDINGS_PROVIDER=$(EMBEDDINGS_PROVIDER) uv run python -m training.build_index

# --- Local cloud simulation ($0, no AWS account) --------------------------------
up: ## Start the local S3 emulator (moto) on :5000
	docker compose up -d

up-ai: ## Start S3 + Ollama embeddings on :11434
	docker compose --profile ai up -d

down: ## Stop every local service
	docker compose --profile "*" down

upload-local: ## Upload artifacts/ to the local S3 (needs: source src/scripts/local-env.sh)
	uv run python src/scripts/upload_model.py --create-bucket

lambda-build: ## Build the Lambda package (build/lambda + build/lambda.zip)
	uv run python src/scripts/build_lambda.py

lambda-up: lambda-build ## Build and (re)start the local Lambda emulator on :9000
	docker compose --profile lambda up -d --force-recreate lambda

lambda-logs: ## Follow the local Lambda logs
	docker compose logs -f lambda

# --- Load testing ---------------------------------------------------------------
smoke: ## k6 smoke test (BASE_URL=... to target another API)
	docker compose --profile loadtest run --rm -e BASE_URL=$(BASE_URL) -e PROFILE=smoke k6

load: ## k6 load profile: ramp to 1,000 VUs, hold 10 min (BASE_URL=...)
	docker compose --profile loadtest run --rm -e BASE_URL=$(BASE_URL) -e PROFILE=load k6

# --- AWS (real resources, real cost) ----------------------------------------------
aws-guard:
	@if [ -n "$$S3_ENDPOINT_URL" ]; then \
		echo "S3_ENDPOINT_URL is set: this shell is in local mode (local-env.sh)."; \
		echo "Open a new shell without it before talking to AWS."; exit 1; \
	fi

deploy: aws-guard lambda-build ## Terraform init + apply (shows the plan and asks for confirmation)
	$(TF) init
	$(TF) apply

upload-aws: aws-guard ## Upload artifacts/ to the bucket created by Terraform
	uv run python src/scripts/upload_model.py --bucket "$$($(TF) output -raw artifacts_bucket)"

api-url: ## Print the public API URL
	@$(TF) output -raw api_url; echo

destroy: aws-guard ## Destroy every AWS resource created by Terraform
	$(TF) destroy

clean: ## Remove build output and caches
	rm -rf build .pytest_cache .ruff_cache
