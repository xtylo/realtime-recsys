import os
from pathlib import Path

from langchain_core.vectorstores import InMemoryVectorStore

from app.infrastructure.aws import s3_client
from app.infrastructure.embeddings import get_embeddings

INDEX_FILE = "search_index.json"


def load_search_index() -> InMemoryVectorStore:
    if os.getenv("ARTIFACTS_SOURCE") == "s3":
        path = Path("/tmp") / INDEX_FILE  # /tmp is the only writable disk on Lambda
        bucket = os.environ["ARTIFACTS_BUCKET"]
        prefix = os.getenv("ARTIFACTS_PREFIX", "models/v1")
        s3_client().download_file(bucket, f"{prefix}/{INDEX_FILE}", str(path))
    else:
        path = Path(os.getenv("ARTIFACTS_DIR", "artifacts")) / INDEX_FILE

    # Query the index with the SAME embeddings provider that built it
    return InMemoryVectorStore.load(str(path), get_embeddings())
