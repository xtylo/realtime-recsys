# 0004. Deploy Lambda as a zip package stored in S3 (not a container image)

- Status: accepted
- Date: 2026-10-22

## Context

The Lambda function runs FastAPI + Mangum, boto3, LangChain (core, Ollama and AWS integrations) and numpy. Lambda accepts two package types:

| Option | Limits | Needs |
|---|---|---|
| **Zip** | 50 MB zipped for direct upload; **250 MB unzipped** when the zip comes from S3 | A package built for Linux x86_64 / Python 3.12 |
| **Container image** | Up to 10 GB | Docker build + an ECR repository + pushing the image before the function exists |

The built package measures **~45 MB zipped** (44.5 MB) and **~124 MB unzipped**, close to the direct-upload limit.

## Decision

- Build a **zip** with `src/scripts/build_lambda.py`. It runs `uv export` from `uv.lock` (runtime dependencies only), then `uv pip install --target build/lambda --python-platform x86_64-manylinux_2_28 --python-version 3.12 --only-binary :all:`, and adds `app/` and `handler.py`.
- Terraform uploads it to the artifacts bucket (`aws_s3_object.lambda_package`) and points the function at it (`s3_bucket` / `s3_key`), with `source_code_hash` to redeploy only on change.
- Run it locally by mounting `build/lambda` into the official Lambda Python image (RIE), so the **same artifact** is tested locally and deployed.

## Alternatives considered

- **Direct zip upload:** simplest, but the package sits at the 50 MB limit and would break as soon as a dependency grows.
- **Container image (ECR):** removes the size concern and gives full control of the OS. But it needs an ECR repository, a two-step bootstrap (repository → push → function) and a Docker build in the deploy path: more moving parts for a learning project.
- **Lambda layers:** split dependencies from code, but add versioning overhead for a single function.

## Consequences

- **Positive:** one Terraform `apply` deploys everything, with no registry. The build is cross-platform (Linux wheels are downloaded from Windows or macOS) and reproducible from `uv.lock`. CI verifies on every push that the package builds (`make lambda-build`).
- **Negative:** only binary wheels (`--only-binary :all:`), so a dependency without manylinux wheels would force a container image. The 250 MB unzipped limit is the ceiling for future dependencies. Cold starts load ~124 MB of Python packages, which contributes to the measured 3.36 s init.
- **Revisit when:** the package approaches 250 MB unzipped, a dependency needs system libraries, or cold-start tuning (SnapStart, slimmer dependencies) makes a different packaging worthwhile.
