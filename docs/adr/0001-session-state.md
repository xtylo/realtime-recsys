# 0001. Session state: in-memory store now, DynamoDB in production

- Status: accepted
- Date: 2026-10-15

## Context

Recommendations depend on the current shopping session: the last 20 events (`view`, `cart`, `purchase`) of a `session_id`. Today that history lives in `InMemorySessionStore`, a dictionary inside the Python process.

The API runs on AWS Lambda, and Lambda's execution model breaks that assumption:

- An execution environment (instance) handles **one request at a time**. Concurrent requests are served by **separate instances**, each with its own memory.
- Instances are created and destroyed by AWS at any time: scale-out, idle timeout, deployments, failures.
- There is no sticky routing: two consecutive requests of the same user can land on different instances.

Observed locally with the Lambda Runtime Interface Emulator (Day 5):

| Measurement | Result |
|---|---|
| First invocation (cold start: Python imports + `init_state` loading artifacts from S3) | **~14.2 s** (`INIT REPORT durationMs: 14219`) |
| Next invocations (warm) | **2.5 – 6.3 ms** |
| Session after `docker compose restart lambda` (= new instance) | **Lost**: the recommendations fell back to popular items |

The 14.2 s cold start is inflated by the local setup: Docker on Windows reading thousands of package files from a bind mount, plus the RIE. Note that the RIE's `REPORT` line shows a misleading `Init Duration: 0.61 ms`, and `Memory Size` is an emulator default. On AWS (Day 8) the cold start was 3.36 s on average, with a peak of 275 concurrent instances during the load test. The key finding holds regardless: **state stored in Lambda memory survives only while that one instance is warm.**

## Decision

1. **Keep `InMemorySessionStore` for the foundation (Days 1–8)**: local development, tests and the first deployment. It is simple, fast and enough to demonstrate the behavior.
2. **Move session state to Amazon DynamoDB for production**, behind the same interface (`add(session_id, product_id, event_type)` / `get(session_id)`), selected by configuration.

Proposed DynamoDB design:

| Attribute | Value |
|---|---|
| Table | `sessions`, on-demand capacity |
| Partition key | `session_id` |
| Sort key | `ts` (event timestamp, ms) |
| Item | `product_id`, `event_type` |
| TTL | `expires_at` = now + 30 min (expired sessions are deleted for free) |
| Read | `Query(session_id, ScanIndexForward=False, Limit=20)`: the last 20 events |

One item per event (instead of a list in a single item) avoids read-modify-write races and the 400 KB item limit. "Last 20" is a cheap reverse query.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| **In-memory (current)** | Fastest, zero cost, zero infrastructure | State lost across instances and restarts. Incorrect under real traffic |
| **DynamoDB** (chosen) | Serverless, pay per request, single-digit ms latency, built-in TTL, no VPC | +1 network call per request (~5–10 ms), cost per read and write |
| ElastiCache (Redis/Valkey) | Sub-ms latency, native lists and TTL | Requires a VPC for the Lambda (more cold start and networking), always-on cost |
| Client-side session (the front end sends its recent events with each request) | Fully stateless API, no storage | Larger requests, the client can tamper with history, logic duplicated in every client |

## Consequences

- **Positive:** correct recommendations regardless of which instance serves the request. Lambda can scale horizontally without losing context. Sessions expire automatically.
- **Negative:** one extra network hop per request, which still fits the p99 < 200 ms target. One more AWS resource in Terraform and one more IAM permission. Event writes now cost money.
- **To do:** introduce a `SessionStore` protocol, add `DynamoSessionStore` (tested with moto), add the table and `dynamodb:PutItem`/`Query` permissions in Terraform, and choose the store via an environment variable (`SESSION_STORE=memory|dynamodb`).
- **Watch:** DynamoDB latency in the k6 results, and cost per 1M requests.
