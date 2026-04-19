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

class BboxModel(BaseModel):
    """Coordonnées d'un bloc dans le PDF source (visual grounding).

    Système de coordonnées : origine haut-gauche, unité points PDF (1 pt = 1/72").
    Correspond à un élément de ``position_int`` produit par openingestion.
    """
    page: int = Field(..., description="Numéro de page (0-indexé)")
    x0: int = Field(..., description="Abscisse gauche")
    y0: int = Field(..., description="Ordonnée haut")
    x1: int = Field(..., description="Abscisse droite")
    y1: int = Field(..., description="Ordonnée bas")


class ChunkModel(BaseModel):
    source: str
    page_content: str
    page_idx: int = 0
    kind: str = "text"
    title_path: str = ""
    chunk_index: int = 0
    rerank_score: Optional[float] = None
    score: Optional[float] = None
    bboxes: list[BboxModel] = Field(
        default_factory=list,
        description="Localisation dans le PDF source — liste de boîtes englobantes",
    )
    pdf_url: Optional[str] = Field(
        None,
        description="URL présignée pour télécharger le PDF source (valide ~1h)",
    )


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
    pdf_url: Optional[str] = Field(
        None,
        description="URL pour accéder au PDF ingéré (présignée MinIO ou endpoint local)",
    )


# ── Réponses sources ───────────────────────────────────────────────────────────

class SourceItem(BaseModel):
    source: str
    name: str
    n_chunks: int


class SourcesResponse(BaseModel):
    sources: list[SourceItem]
    total_chunks: int


# ── Feedback ───────────────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    """Corps de la requête POST /feedback.

    Envoyé depuis l'UI quand l'utilisateur note et commente une réponse LLM.
    """
    question_id: str = Field(..., description="Identifiant unique de la question (UnifiedRAGState.question_id)")
    question: str = Field(..., min_length=1, max_length=4000, description="Question posée")
    answer: str = Field(..., min_length=1, description="Réponse du LLM")
    rating: int = Field(..., ge=1, le=5, description="Note de 1 (mauvais) à 5 (excellent)")
    comment: Optional[str] = Field(None, description="Commentaire libre de l'utilisateur")
    user_id: str = Field("anonymous", description="Identifiant de l'utilisateur")
    conversation_title: Optional[str] = Field(None, description="Titre généré par le LLM")
    sources: list[ChunkModel] = Field(default_factory=list, description="Documents sources utilisés")
    decision_log: list[dict[str, Any]] = Field(default_factory=list, description="Journal des décisions de l'agent")
    follow_up_suggestions: list[str] = Field(default_factory=list, description="Suggestions de questions de suivi")
    n_retrieved: int = Field(0, ge=0, description="Nombre de chunks récupérés")


class FeedbackResponse(BaseModel):
    """Réponse après enregistrement du feedback."""
    conversation_id: str
    message_id: str
    rating: int
    comment: Optional[str] = None


class ConversationItem(BaseModel):
    """Vue synthétique d'une conversation pour la liste GET /feedback."""
    conversation_id: str
    user_id: str
    title: Optional[str] = None
    question_id: Optional[str] = None
    created_at: str
    message_count: int
