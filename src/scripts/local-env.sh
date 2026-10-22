# Environment variables for local development (no AWS account needed).
# The services (S3 emulator, Ollama) run with docker compose; see docker-compose.yml.
#
# Usage: source it, so the variables apply to the current shell:
#   source src/scripts/local-env.sh
#
# Windows PowerShell equivalent: . .\src\scripts\local-env.ps1

export AWS_ACCESS_KEY_ID=test          # moto accepts any credentials
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1
export ARTIFACTS_SOURCE=s3
export ARTIFACTS_BUCKET=recsys-local
export ARTIFACTS_PREFIX=models/v1
export S3_ENDPOINT_URL=http://localhost:5000
export EMBEDDINGS_PROVIDER=ollama
export OLLAMA_URL=http://localhost:11434
export ENABLE_SEARCH="${ENABLE_SEARCH:-true}"   # requires Ollama: docker compose --profile ai up -d

echo "Local mode on: S3 -> $S3_ENDPOINT_URL | embeddings -> $OLLAMA_URL | search: $ENABLE_SEARCH"
