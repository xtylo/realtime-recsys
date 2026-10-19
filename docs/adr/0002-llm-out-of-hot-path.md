# 0002. Keep generative LLMs out of the hot path; use an embeddings model for search

- Status: accepted
- Date: 2026-10-18

## Context

The project pitch mentions LangChain and AI-driven recommendations. The obvious design would be to send the user's session to a generative LLM (a chat model such as GPT, Claude or Llama) on every request: *"this user viewed X and Y, recommend 10 products"*.

The system has hard non-functional targets (see README → Target metrics):

| Target | Value |
|---|---|
| Peak throughput | ~2,000 req/s (1M daily users) |
| Latency | p99 < 200 ms |
| Error rate | < 0.1% |

Two features need "intelligence":

1. **`GET /recommendations`**: called on every page view, so it is the hot path.
2. **`POST /search`**: natural-language product search ("cheap samsung headphones"), called far less often.

## Decision

1. **Recommendations do not call any LLM.** They are computed from pre-built artifacts (`related.json`, `popular.json`) with in-memory lookups and simple arithmetic. See the recommender in `src/app/domain/recommender.py`.
2. **Search uses an embeddings model, not a generative model.** It goes through LangChain's `Embeddings` interface (`src/app/infrastructure/embeddings.py`):
   - Product descriptions are embedded **offline**, once, into `search_index.json` (an artifact in S3).
   - At request time, only the user's query is embedded (one small model call), then ranked by cosine similarity against the stored vectors.
3. **Provider by environment**, chosen with `EMBEDDINGS_PROVIDER`:
   - Local development: **Ollama** + `nomic-embed-text`. It runs on the developer machine, costs $0, works offline and needs no AWS account.
   - AWS: **Amazon Bedrock** + Titan Text Embeddings V2. It is managed, accessed through IAM and needs no API keys.

   An index must be queried with the same model that built it, so the index is rebuilt when the provider changes.

## Why not a generative LLM per request

| Concern | Generative LLM per request | Chosen design |
|---|---|---|
| **Latency** | Typically hundreds of ms to several seconds per call (prompt processing + token generation). Alone, it breaks p99 < 200 ms. | Recommendations: microseconds of compute after warm-up (measured 2.5–6 ms per Lambda invocation locally). Search: one embedding call + an in-memory similarity scan. |
| **Cost at scale** | Billed per token on every request. Illustrative: 1M users × ~20 requests/day × ~500 tokens ≈ 10B tokens/day. | Recommendations: no per-request model cost. Search: one short embedding per query, and embeddings are far cheaper than generation. |
| **Throughput / quotas** | Provider rate limits and concurrency quotas become the system's ceiling at ~2,000 req/s. | Scales with Lambda, with no external model in the recommendation path. |
| **Correctness** | Can invent product IDs that do not exist (hallucination). Output must be parsed and validated. | Can only return real catalog IDs from the artifacts. |
| **Determinism & testing** | Same input can produce different outputs, which makes unit tests and regressions hard. | Deterministic: covered by plain pytest assertions. |
| **Availability** | One more external dependency in the critical path. | Recommendations keep working even if the model provider is down. Only `/search` depends on it. |

## Where generative LLMs *are* acceptable

Off the hot path, where latency and per-request cost do not matter:

- **Offline enrichment:** generate better product descriptions or tags before indexing, which improves search quality.
- **Asynchronous explanations:** "Because you viewed X…", generated in the background and cached per product pair.
- **Query understanding for `/search` only:** extract structured filters (`brand`, `max_price`) from the query, with caching. This is LangChain's self-query retriever pattern.

## Consequences

- **Positive:** the latency and cost targets are reachable. The hot path is deterministic and testable. LangChain's `Embeddings` abstraction lets us swap Ollama ↔ Bedrock (or another provider) without touching the endpoints.
- **Negative:** recommendations are less "intelligent" than an LLM could be: they cannot reason about intent or explain themselves. Search quality is limited by the poor product descriptions (category + brand + price only) and by the lack of numeric understanding ("cheap" is not mapped to a price range).
- **Operational:** the search index must be rebuilt whenever the embeddings model changes. Ollama must be running for local search, and Bedrock model access must be enabled in AWS (Day 8).
- **To measure:** `/search` latency (embedding call + similarity scan) locally and on AWS, and cost per 1M searches with Bedrock.
- **Possible improvements:** use `nomic-embed-text` task prefixes (`search_document:` / `search_query:`), richer product text, and a vector database (FAISS, pgvector, OpenSearch) when the catalog grows beyond what a brute-force in-memory scan can handle.
