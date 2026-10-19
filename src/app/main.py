import os
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request

from app.domain.recommender import Recommender
from app.infrastructure.artifacts import load_artifacts
from app.infrastructure.search import load_search_index
from app.infrastructure.session_store import InMemorySessionStore
from app.schemas import Event, Recommendation, SearchRequest, SearchResult


def init_state(app: FastAPI) -> None:
    """Load the model and create shared objects. Runs once per process (or Lambda cold start)."""
    related, popular = load_artifacts()
    app.state.recommender = Recommender(related, popular)
    app.state.sessions = InMemorySessionStore()
    app.state.search_index = load_search_index() if os.getenv("ENABLE_SEARCH") == "true" else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_state(app)  # uvicorn and TestClient. Lambda calls init_state from handler.py instead.
    yield


app = FastAPI(title="RealTime RecSys", lifespan=lifespan)


def get_recommender(request: Request) -> Recommender:
    return request.app.state.recommender


def get_sessions(request: Request) -> InMemorySessionStore:
    return request.app.state.sessions


RecommenderDep = Annotated[Recommender, Depends(get_recommender)]
SessionsDep = Annotated[InMemorySessionStore, Depends(get_sessions)]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/events", status_code=202)
def track_event(event: Event, sessions: SessionsDep):
    sessions.add(event.session_id, event.product_id, event.event_type)
    return {"accepted": True}


@app.get("/recommendations", response_model=list[Recommendation])
def recommendations(session_id: str, recommender: RecommenderDep, sessions: SessionsDep, k: int = 10):
    history = sessions.get(session_id)
    return [Recommendation(product_id=p, score=s) for p, s in recommender.recommend(history, k)]


@app.post("/search", response_model=list[SearchResult])
def search(req: SearchRequest, request: Request):
    index = request.app.state.search_index
    if index is None:
        raise HTTPException(status_code=503, detail="Search is disabled")
    results = index.similarity_search_with_score(req.query, k=req.k)
    return [
        SearchResult(product_id=doc.metadata["product_id"], description=doc.page_content, similarity=float(score))
        for doc, score in results
    ]
