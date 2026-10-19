"""Build a semantic product index with LangChain."""

import os

import pandas as pd
from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore

from app.infrastructure.embeddings import get_embeddings

MAX_PRODUCTS = 5_000


def describe(row) -> str:
    category = row.category_code if pd.notna(row.category_code) else "unknown category"
    brand = row.brand if pd.notna(row.brand) else "unknown brand"
    return f"{category.replace('.', ' ')} {brand} price {row.price:.2f} USD"


def main() -> None:
    products = pd.read_parquet("data/processed/products.parquet").head(MAX_PRODUCTS)
    docs = [
        Document(page_content=describe(r), metadata={"product_id": int(r.product_id)}) for r in products.itertuples()
    ]
    index = InMemoryVectorStore.from_documents(docs, get_embeddings())
    index.dump("artifacts/search_index.json")
    print(f"indexed={len(docs):,} provider={os.getenv('EMBEDDINGS_PROVIDER', 'ollama')}")


if __name__ == "__main__":
    main()
