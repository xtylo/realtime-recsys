"""Request and response models (Pydantic). They validate input and generate the OpenAPI schema."""

from typing import Literal

from pydantic import BaseModel, Field

EventType = Literal["view", "cart", "purchase"]


class Event(BaseModel):
    """A user interaction sent by the storefront."""

    session_id: str = Field(description="Shopping session identifier.", examples=["s1"])
    product_id: int = Field(description="Product the user interacted with.", examples=[1004856])
    event_type: EventType = Field(description="Interaction type: view < cart < purchase in weight.")


class Recommendation(BaseModel):
    product_id: int
    score: float = Field(description="Relevance score. 0.0 means a popular-item fallback.")


class SearchRequest(BaseModel):
    query: str = Field(description="Free-text query (English works best).", examples=["cheap samsung headphones"])
    k: int = Field(10, description="Number of results.")


class SearchResult(BaseModel):
    product_id: int
    description: str = Field(description="The product text that was embedded.")
    similarity: float = Field(description="Cosine similarity: higher = more similar.")
