from typing import Literal

from pydantic import BaseModel

EventType = Literal["view", "cart", "purchase"]


class Event(BaseModel):
    session_id: str
    product_id: int
    event_type: EventType


class Recommendation(BaseModel):
    product_id: int
    score: float


class SearchRequest(BaseModel):
    query: str
    k: int = 10


class SearchResult(BaseModel):
    product_id: int
    description: str
    similarity: float  # cosine: higher = more similar
