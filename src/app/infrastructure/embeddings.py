"""Embeddings provider factory (LangChain `Embeddings` interface).

EMBEDDINGS_PROVIDER=ollama (default): `nomic-embed-text` on a local Ollama server (OLLAMA_URL).
EMBEDDINGS_PROVIDER=bedrock: Amazon Titan Text Embeddings V2 on Bedrock (AWS credentials/IAM role).

Callers only see `Embeddings`, so swapping providers does not touch the rest of the code.
An index must be queried with the same provider that built it.
"""

import os

from langchain_core.embeddings import Embeddings


def get_embeddings() -> Embeddings:
    provider = os.getenv("EMBEDDINGS_PROVIDER", "ollama")

    if provider == "ollama":
        from langchain_ollama import OllamaEmbeddings

        return OllamaEmbeddings(
            model="nomic-embed-text",
            base_url=os.getenv("OLLAMA_URL") or "http://localhost:11434",
        )
    if provider == "bedrock":
        from langchain_aws import BedrockEmbeddings

        return BedrockEmbeddings(model_id="amazon.titan-embed-text-v2:0")

    raise ValueError(f"Unsupported EMBEDDINGS_PROVIDER: {provider}")
