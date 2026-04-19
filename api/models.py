"""Modèles Pydantic — requêtes et réponses de l'API RAG."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Requêtes ───────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000, description="Question de l'utilisateur")
    source_filter: Optional[str] = Field(None, description="Restreindre la recherche à ce chemin source")
    conversation_summary: str = Field("", description="Résumé des tours précédents")


# ── Modèles de données ─────────────────────────────────────────────────────────

class ChunkModel(BaseModel):
    source: str
    page_content: str
    page_idx: int = 0
    kind: str = "text"
    title_path: str = ""
    chunk_index: int = 0
    rerank_score: Optional[float] = None
    score: Optional[float] = None


# ── Réponses query ─────────────────────────────────────────────────────────────

class QueryResponse(BaseModel):
    question_id: str
    question: str
    answer: str
    sources: list[ChunkModel] = []
    follow_up_suggestions: list[str] = []
    conversation_title: Optional[str] = None
    n_retrieved: int = 0
    decision_log: list[dict[str, Any]] = []
    error: Optional[str] = None


class StreamEvent(BaseModel):
    """Événement SSE émis nœud par nœud pendant le streaming."""
    type: str  # "node_update" | "answer" | "done" | "error"
    node: Optional[str] = None
    message: Optional[str] = None
    answer: Optional[str] = None
    sources: list[ChunkModel] = []
    follow_up_suggestions: list[str] = []
    conversation_title: Optional[str] = None
    error: Optional[str] = None


# ── Réponses ingestion ─────────────────────────────────────────────────────────

class IngestResponse(BaseModel):
    n_chunks: int
    source: str
    filename: str


# ── Réponses sources ───────────────────────────────────────────────────────────

class SourceItem(BaseModel):
    source: str
    name: str
    n_chunks: int


class SourcesResponse(BaseModel):
    sources: list[SourceItem]
    total_chunks: int
