# Code walkthrough

A guided tour of the code: what each file does, who calls it, and how to extend it. For the big picture (flows, algorithm, configuration), read [ARCHITECTURE.md](ARCHITECTURE.md) first.

## Suggested reading order

1. `src/app/schemas.py`: the API's data shapes.
2. `src/app/main.py`: endpoints, startup, dependency injection.
3. `src/app/domain/recommender.py`: the ranking logic (the heart of the system).
4. `src/app/infrastructure/*`: where data comes from (files, S3, embeddings).
5. `src/lambda/handler.py`: how the same app runs on AWS Lambda.
6. `src/training/*`: how the artifacts are built.
7. `tests/*`: executable examples of all of the above.

## Map of the repository

| Path | Role | Called by | Concepts it shows |
|---|---|---|---|
| `src/app/main.py` | FastAPI app, endpoints, `init_state`, DI providers | uvicorn, `handler.py`, tests | Composition root, `lifespan`, `Depends` |
| `src/app/schemas.py` | Pydantic request/response models | `main.py` | Validation, 422 errors, OpenAPI |
| `src/app/domain/recommender.py` | Scoring and ranking | `main.py` | Pure domain logic, no I/O |
| `src/app/infrastructure/session_store.py` | Last 20 events per session | `main.py` | In-memory state (see ADR 0001) |
| `src/app/infrastructure/artifacts.py` | Load `related.json` / `popular.json` | `init_state` | Local vs S3 by configuration |
| `src/app/infrastructure/aws.py` | Build the boto3 S3 client | `artifacts.py`, `search.py` | One switch for moto vs real S3 |
| `src/app/infrastructure/embeddings.py` | Choose Ollama or Bedrock | `search.py`, `build_index.py` | Provider abstraction (LangChain `Embeddings`) |
| `src/app/infrastructure/search.py` | Load the vector index | `init_state` | `InMemoryVectorStore`, temp dir on Lambda |
| `src/lambda/handler.py` | Lambda entry point | AWS Lambda / RIE | Mangum adapter, cold-start init |
| `src/training/build_artifacts.py` | Popular items + co-occurrence | `make artifacts` | pandas `groupby`, item-to-item CF |
| `src/training/build_index.py` | Embed products into a search index | `make index` | Embeddings, vector store |
| `src/scripts/build_lambda.py` | Build the Linux deployment package | `make lambda-build`, CI | Cross-platform wheels with `uv pip --python-platform` |
| `src/scripts/invoke_lambda.py` | Call the local Lambda like API Gateway | you, tests | API Gateway v2 event format |
| `src/scripts/upload_model.py` | Upload `artifacts/` to S3 | `make upload-local` / `upload-aws` | boto3 uploads, local vs AWS |
| `src/scripts/local-env.sh` / `.ps1` | Local-mode environment variables | `source` | 12-factor configuration |
| `src/infra/terraform/*.tf` | AWS infrastructure | `make deploy` | IaC, least-privilege IAM |
| `docker-compose.yml` | Local S3, Ollama, Lambda emulator, k6 | `make up*`, `make lambda-up`, `make smoke` | Compose profiles, service DNS |
| `loadtest/k6.js` | Load test (smoke / load profiles) | `make smoke` / `make load` | Closed-model load, thresholds |
| `tests/*` | Unit + integration tests | `make test`, CI | Fixtures, mocks, TestClient |
| `Makefile` | Shortcuts for every task | you, CI | — |

## The application (`src/app`)

### `schemas.py`
Pydantic models are the API contract. FastAPI uses them to **parse and validate** input: `event_type` must be `view`, `cart` or `purchase`, and `k` must be an integer. Invalid input gets a 422 automatically, with the failing field in `loc`. The same models generate the OpenAPI schema ([`docs/openapi.json`](openapi.json), `make openapi`).

### `main.py`
Three parts:

1. **`init_state(app)`** builds the shared objects once: the `Recommender` (from the artifacts), the session store and, if `ENABLE_SEARCH=true`, the search index. They live in `app.state`.
2. **`lifespan`** calls `init_state` when uvicorn (or `TestClient`) starts. Lambda does not use it (see `handler.py`).
3. **Endpoints** declare their dependencies with type hints:
   ```python
   RecommenderDep = Annotated[Recommender, Depends(get_recommender)]

   @app.get("/recommendations", response_model=list[Recommendation])
   def recommendations(session_id: str, recommender: RecommenderDep, sessions: SessionsDep, k: int = 10):
   ```
   FastAPI calls `get_recommender(request)` and passes the result in. It is the equivalent of constructor or parameter injection in ASP.NET Core. Query parameters (`session_id`, `k`) come from the URL; the JSON body is parsed into a Pydantic model (`Event`, `SearchRequest`).

Endpoints are thin: they translate HTTP ↔ domain and contain no business rules.

### `domain/recommender.py`
`Recommender.recommend(history, k)` implements the scoring explained in [ARCHITECTURE.md §4](ARCHITECTURE.md#4-the-recommendation-algorithm):

```python
for age, (pid, event_type) in enumerate(reversed(history)):      # newest first, age 0, 1, 2…
    weight = EVENT_WEIGHTS[event_type] * (RECENCY_DECAY**age)
    for rank, candidate in enumerate(self._related.get(str(pid), [])):
        if candidate not in seen:                                  # discovery: skip what the user saw
            scores[candidate] += weight / (rank + 1)
```

`Counter.most_common(k)` returns the top `k`; popular products fill the rest. The class only receives plain dicts and lists. It does not know about files, S3 or HTTP, which is why `tests/test_recommender.py` can test it with three-line fixtures.

### `infrastructure/`
Each file wraps one external concern behind a small function, and configuration decides the implementation:

- **`artifacts.py`**: `ARTIFACTS_SOURCE=local` reads `./artifacts`; `s3` reads `s3://ARTIFACTS_BUCKET/ARTIFACTS_PREFIX/`.
- **`aws.py`**: `s3_client()` is the only place that knows about moto. If `S3_ENDPOINT_URL` is set, the client points there (with path-style addressing); if not, it uses real AWS.
- **`session_store.py`**: a `defaultdict` of `deque(maxlen=20)`. It is fast and simple, but each process has its own copy (see [ADR 0001](adr/0001-session-state.md)).
- **`embeddings.py`**: returns a LangChain `Embeddings`. Callers never import Ollama or Bedrock directly.
- **`search.py`**: loads the `InMemoryVectorStore` JSON, from S3 into the OS temp dir (`/tmp` on Lambda, its only writable disk) or from `./artifacts`.

## Running on Lambda (`src/lambda/handler.py`)

```python
init_state(app)                        # module level: once per cold start
handler = Mangum(app, lifespan="off")  # Lambda calls handler(event, context)
```

Lambda does not speak HTTP. API Gateway turns the request into a JSON **event**, Lambda calls `handler(event, context)`, and **Mangum** converts the event into an ASGI request for FastAPI and the response back into `{"statusCode", "headers", "body"}`.

`src/scripts/invoke_lambda.py` builds the same event shape, which is how you talk to the local emulator, and the tests use it too. The folder name `lambda` is a Python keyword, so the folder cannot be imported. `build_lambda.py` copies `handler.py` to the root of the package, and Terraform's `handler = "handler.handler"` means "module `handler`, attribute `handler`".

## Offline training (`src/training`)

- **`build_artifacts.py`**: `pd.read_csv(nrows=200_000)`, weighted `groupby` for popularity, then `itertools.permutations` over each de-duplicated session to count co-occurrences. Output: `artifacts/popular.json`, `artifacts/related.json`, `data/processed/products.parquet`.
- **`build_index.py`**: builds one LangChain `Document` per product (text + `product_id` metadata), embeds them with `get_embeddings()` and dumps the vector store to `artifacts/search_index.json`.

Both are run from the repo root as modules (`python -m training.build_artifacts`), because `uv sync` installs `src/app` and `src/training` as editable packages (see `[tool.hatch.build.targets.wheel]` in `pyproject.toml`).

## Scripts (`src/scripts`)

| Script | What it does |
|---|---|
| `build_lambda.py` | `uv export` the runtime dependencies from `uv.lock`, then `uv pip install --target build/lambda --python-platform x86_64-manylinux_2_28 --python-version 3.12`. Linux wheels are downloaded even on Windows or macOS. It then copies `app/` and `handler.py` and zips the result. Dev dependencies (pandas, pytest, uvicorn…) are excluded. |
| `invoke_lambda.py` | `build_event(method, path, body)` creates an API Gateway HTTP API v2 event; `invoke()` POSTs it to the emulator at `localhost:9000`. |
| `upload_model.py` | Uploads every file under `artifacts/` to `s3://bucket/prefix/...`; `--create-bucket` for moto. |
| `local-env.sh` / `local-env.ps1` | Fake AWS credentials + `S3_ENDPOINT_URL` + bucket/prefix + Ollama URL for local mode. |

## Infrastructure (`src/infra/terraform`)

- `versions.tf`: Terraform and AWS provider versions, plus default tags.
- `variables.tf`: inputs (`artifacts_bucket_name` is required; memory, timeout and `enable_search` have defaults).
- `main.tf`: S3 bucket (+ public access block) and the Lambda zip object, an IAM role with least privilege, the log group, the Lambda function with its environment variables, and the API Gateway HTTP API with a `$default` route and a Lambda permission.
- `outputs.tf`: `api_url`, `artifacts_bucket`, `lambda_function_name`.

## Tests (`tests`)

| File | Proves |
|---|---|
| `conftest.py` | **Autouse fixture**: every test gets a tiny model on disk (`related = {"1": [2, 3]}`, `popular = [9, 8]`) and a clean local-only environment. `client` runs the app with its lifespan |
| `test_recommender.py` | Cold start returns popular items; cart outweighs view; seen products are excluded |
| `test_api.py` | Recommendations change after an event: real time, end to end through HTTP |
| `test_health.py` | Health check and 422 validation |
| `test_artifacts_s3.py` | Loading artifacts from S3, with S3 mocked in memory by `moto.mock_aws` |
| `test_lambda_handler.py` | The Lambda handler with real API Gateway events: 200, 422, and the session surviving between warm invocations |

None of them needs Docker, Ollama or AWS, which is why CI is just `make check`.

## How to extend it

### Add an endpoint
Example: `GET /popular?k=10`.
1. Domain (`recommender.py`): add a method, with no I/O.
   ```python
   def popular(self, k: int = 10) -> list[int]:
       return self._popular[:k]
   ```
2. API (`main.py`): declare the endpoint and its dependencies.
   ```python
   @app.get("/popular", response_model=list[int])
   def popular(recommender: RecommenderDep, k: int = 10):
       """Most popular products (no personalization)."""
       return recommender.popular(k)
   ```
3. Test it with the `client` fixture (`popular` is `[9, 8]` there), then run `make check` and `make openapi`.

### Replace the in-memory session store with DynamoDB
This is the production fix from [ADR 0001](adr/0001-session-state.md).
1. Define the contract the endpoints depend on (a `Protocol` works like an interface):
   ```python
   class SessionStore(Protocol):
       def add(self, session_id: str, product_id: int, event_type: str) -> None: ...
       def get(self, session_id: str) -> list[tuple[int, str]]: ...
   ```
2. Implement it, with one item per event, sort key `ts` and a TTL attribute:
   ```python
   class DynamoSessionStore:
       def __init__(self, table_name: str, max_events: int = 20, ttl_seconds: int = 1800):
           self._table = boto3.resource("dynamodb").Table(table_name)
           self._max_events = max_events
           self._ttl_seconds = ttl_seconds

       def add(self, session_id: str, product_id: int, event_type: str) -> None:
           now_ms = time.time_ns() // 1_000_000
           self._table.put_item(Item={
               "session_id": session_id, "ts": now_ms,
               "product_id": product_id, "event_type": event_type,
               "expires_at": now_ms // 1000 + self._ttl_seconds,   # DynamoDB TTL attribute
           })

       def get(self, session_id: str) -> list[tuple[int, str]]:
           response = self._table.query(
               KeyConditionExpression=Key("session_id").eq(session_id),
               ScanIndexForward=False, Limit=self._max_events,      # newest 20
           )
           return [(int(i["product_id"]), i["event_type"]) for i in reversed(response["Items"])]
   ```
   Two events in the same millisecond would overwrite each other. Add a random suffix to the sort key if that matters.
3. Choose the store in `init_state` with `SESSION_STORE=memory|dynamodb` and type `SessionsDep` as `SessionStore`.
4. Terraform: an `aws_dynamodb_table` (`PAY_PER_REQUEST`, hash `session_id`, range `ts`, TTL on `expires_at`) plus `dynamodb:PutItem` and `dynamodb:Query` in the Lambda policy.
5. Test with `moto` (`uv add --dev "moto[dynamodb]"`), the same way `test_artifacts_s3.py` mocks S3.

### Use another embeddings provider
Add a branch in `embeddings.py` (for example `langchain-openai`'s `OpenAIEmbeddings`), set `EMBEDDINGS_PROVIDER`, **rebuild the index** with `make index` and re-upload it. Nothing else changes.

### Ship a new model version
Write the new artifacts under a new prefix (`--prefix models/v2` in `upload_model.py`) and switch `ARTIFACTS_PREFIX`. Rolling back means switching the variable back. The Terraform IAM policy currently allows only `models/v1/*`, so widen it when you start versioning.

## If you come from .NET

| Here | .NET equivalent |
|---|---|
| `uv` + `pyproject.toml` + `uv.lock` | `dotnet` CLI + `.csproj` + `packages.lock.json` |
| FastAPI + Pydantic | Minimal APIs + records / DataAnnotations |
| `Depends()` / `app.state` | DI container / singletons |
| `lifespan` | `IHostedService.StartAsync` / `Program.cs` startup |
| Mangum + `handler.py` | `Amazon.Lambda.AspNetCoreServer` `LambdaEntryPoint` |
| pytest fixtures / `monkeypatch` | xUnit fixtures / test doubles |
| moto | Azurite / in-memory fakes |
| Terraform | Bicep / ARM |
