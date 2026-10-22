"""Load the recommender artifacts (`related.json`, `popular.json`) from local files or S3.

ARTIFACTS_SOURCE=local (default) reads ARTIFACTS_DIR (default: ./artifacts).
ARTIFACTS_SOURCE=s3 reads s3://ARTIFACTS_BUCKET/ARTIFACTS_PREFIX/ (real AWS, or moto when S3_ENDPOINT_URL is set).
"""

import json
import os
from pathlib import Path

from app.infrastructure.aws import s3_client


def load_artifacts() -> tuple[dict[str, list[int]], list[int]]:
    """Return (related, popular)."""
    if os.getenv("ARTIFACTS_SOURCE", "local") == "s3":
        bucket = os.environ["ARTIFACTS_BUCKET"]
        prefix = os.getenv("ARTIFACTS_PREFIX", "models/v1")
        s3 = s3_client()

        def read(name: str):
            obj = s3.get_object(Bucket=bucket, Key=f"{prefix}/{name}")
            return json.loads(obj["Body"].read())
    else:
        base = Path(os.getenv("ARTIFACTS_DIR", "artifacts"))

        def read(name: str):
            return json.loads((base / name).read_text())

    return read("related.json"), read("popular.json")
