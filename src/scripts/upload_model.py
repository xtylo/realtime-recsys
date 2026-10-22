"""Upload the local model artifacts (artifacts/ folder) to S3.

Works against real AWS, or against the local S3 emulator (moto) when
S3_ENDPOINT_URL is set (see src/scripts/local-env.sh and docker-compose.yml).

Usage:
    uv run python src/scripts/upload_model.py --create-bucket       # local S3 (moto)
    uv run python src/scripts/upload_model.py --bucket my-bucket     # real AWS (bucket created by Terraform)
"""

import argparse
import os
import sys
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


def s3_client(endpoint_url: str | None):
    # Path-style addressing (http://host:5000/bucket/key) is what local emulators expect.
    config = Config(s3={"addressing_style": "path"}) if endpoint_url else None
    region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    return boto3.client("s3", endpoint_url=endpoint_url, region_name=region, config=config)


def ensure_bucket(s3, bucket: str) -> None:
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError:
        s3.create_bucket(Bucket=bucket)
        print(f"created bucket s3://{bucket}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=Path("artifacts"), help="Local folder to upload")
    parser.add_argument("--bucket", default=os.getenv("ARTIFACTS_BUCKET", "recsys-local"))
    parser.add_argument("--prefix", default=os.getenv("ARTIFACTS_PREFIX", "models/v1"))
    parser.add_argument("--endpoint-url", default=os.getenv("S3_ENDPOINT_URL") or None,
                        help="S3 endpoint (empty = real AWS)")
    parser.add_argument("--create-bucket", action="store_true", help="Create the bucket if it does not exist")
    args = parser.parse_args()

    files = sorted(p for p in args.source.rglob("*") if p.is_file()) if args.source.is_dir() else []
    if not files:
        sys.exit(f"No files found in '{args.source}'. Run the training scripts first (see docs/PLAN.md).")

    s3 = s3_client(args.endpoint_url)
    if args.create_bucket:
        ensure_bucket(s3, args.bucket)

    for path in files:
        key = f"{args.prefix}/{path.relative_to(args.source).as_posix()}"
        s3.upload_file(str(path), args.bucket, key)
        print(f"uploaded s3://{args.bucket}/{key}")

    print(f"\n{len(files)} file(s) uploaded to {args.endpoint_url or 'AWS'}")


if __name__ == "__main__":
    main()
