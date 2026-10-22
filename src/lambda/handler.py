"""AWS Lambda entry point (Terraform handler setting: "handler.handler").

Mangum translates API Gateway HTTP API (payload v2) events into ASGI requests for the FastAPI app,
and the app's responses back into the dict Lambda returns to API Gateway.

`init_state` runs at module level: once per cold start, reused while the instance stays warm.
Mangum would run the FastAPI lifespan on every invocation, hence lifespan="off".

This folder is named `lambda` (a Python keyword), so it is not an importable package:
`src/scripts/build_lambda.py` copies this file to the root of the deployment package.
"""

from mangum import Mangum

from app.main import app, init_state

init_state(app)  # module level = once per cold start, reused while the instance is warm
handler = Mangum(app, lifespan="off")
