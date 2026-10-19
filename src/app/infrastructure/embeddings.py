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
    if provider == "bedrock":  # used on Day 8
        from langchain_aws import BedrockEmbeddings

        return BedrockEmbeddings(model_id="amazon.titan-embed-text-v2:0")

    raise ValueError(f"Unsupported EMBEDDINGS_PROVIDER: {provider}")
