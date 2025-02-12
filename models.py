import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    """Result from search engine."""

    url: str
    title: str
    snippet: str
    relevance_score: float | int = 0.0


@dataclass
class Chunk:
    content: str
    url: str
    tokens: int
    metadata: dict[str, Any]
    references: str
    chunk_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class SearchContext(BaseModel):
    question: str
    search_queries: set[str] = Field(default_factory=set)
    processed_queries: set[str] = Field(default_factory=set)
    research_goals: set[str] = Field(default_factory=set)
    processed_goals: set[str] = Field(default_factory=set)
    insights: list[str] = Field(default_factory=list)
    followup_questions: list[str] = Field(default_factory=list)
    processed_followup_questions: set[str] = Field(default_factory=set)
    search_results: list[SearchResult] = Field(default_factory=list)
    chunks: list[Chunk] = Field(default_factory=list)
    processed_chunks: set[str] = Field(default_factory=set)
    processed_urls: set[str] = Field(default_factory=set)
    token_usage: int = 0
