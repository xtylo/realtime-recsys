# Environment variables for local development (no AWS account needed).
# The services (S3 emulator, Ollama) run with docker compose; see docker-compose.yml.
#
# Usage - note the leading dot, so the variables apply to the current terminal:
#   . .\src\scripts\local-env.ps1
#
# Bash (Linux, macOS, WSL, Git Bash, Dev Container): source src/scripts/local-env.sh

$env:AWS_ACCESS_KEY_ID     = "test"      # moto accepts any credentials
$env:AWS_SECRET_ACCESS_KEY = "test"
$env:AWS_DEFAULT_REGION    = "us-east-1"
$env:ARTIFACTS_SOURCE      = "s3"
$env:ARTIFACTS_BUCKET      = "recsys-local"
$env:ARTIFACTS_PREFIX      = "models/v1"
$env:S3_ENDPOINT_URL       = "http://localhost:5000"
$env:EMBEDDINGS_PROVIDER   = "ollama"
$env:OLLAMA_URL            = "http://localhost:11434"
$env:ENABLE_SEARCH         = "true"     # requires Ollama: docker compose --profile ai up -d

Write-Host "Local mode on: S3 -> $env:S3_ENDPOINT_URL | embeddings -> $env:OLLAMA_URL"
