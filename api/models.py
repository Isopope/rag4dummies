"""Modèles Pydantic — requêtes et réponses de l'API RAG."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Requêtes ───────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000, description="Question de l'utilisateur")
    source_filter: Optional[str] = Field(None, description="Restreindre la recherche à ce chemin source")
    conversation_summary: str = Field("", description="Résumé des tours précédents")
    session_id: Optional[str] = Field(None, description="UUID de la session en cours (None = nouvelle session)")
    model: Optional[str] = Field(None, description="Identifiant LiteLLM du modèle (ex: gpt-4o, mistral/mistral-large-latest). Si absent, utilise le modèle par défaut du serveur.")


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
    question_id: Optional[str] = None
    session_id: Optional[str] = None
    error: Optional[str] = None


# ── Réponses ingestion ─────────────────────────────────────────────────────────

class IngestJobResponse(BaseModel):
    """Réponse immédiate après soumission d'une ingestion asynchrone."""
    task_id: str = Field(..., description="Identifiant de la tâche Celery")
    status: str  = Field("pending", description="pending | processing | indexed | error")
    source: str  = Field(..., description="Clé de l'objet dans le DocumentStore")
    filename: str
    pdf_url: Optional[str] = Field(
        None, description="URL présignée du PDF (valide ~1h) — disponible immédiatement"
    )
    chunk_count: int = 0
    error: Optional[str] = None


class JobStatusResponse(BaseModel):
    """Réponse de GET /jobs/{task_id} — état courant de la tâche."""
    task_id: str
    celery_state: str = Field(..., description="PENDING | STARTED | SUCCESS | FAILURE | RETRY")
    status: str       = Field(..., description="pending | processing | indexed | error | unknown")
    source: Optional[str]   = None
    filename: Optional[str] = None
    chunk_count: int  = 0
    pdf_url: Optional[str]  = None
    error: Optional[str]    = None


class IngestResponse(BaseModel):
    n_chunks: int
    source: str
    filename: str
    pdf_url: Optional[str] = Field(
        None,
        description="URL pour accéder au PDF ingéré (présignée MinIO ou endpoint local)",
    )


# ── Connecteurs (crawl) ────────────────────────────────────────────────────────

class CrawlLocalRequest(BaseModel):
    directory: str  = Field(..., description="Chemin absolu du répertoire à scanner")
    ext: list[str]  = Field([".pdf"], description="Extensions acceptées")
    recursive: bool = Field(True, description="Descendre dans les sous-répertoires")
    parser: str     = Field("docling", description="docling | mineru | simple")
    strategy: str   = Field("by_token", description="by_token | by_sentence | by_block")
    entity: Optional[str]        = Field(None, description="Entité propriétaire (ex. 'dassault')")
    validity_date: Optional[str] = Field(None, description="Date de validité ISO YYYY-MM-DD")


class CrawlWebRequest(BaseModel):
    urls: list[str] = Field(..., min_length=1, description="URLs à crawler (Playwright → PDF)")
    output_dir: str = Field("./tmp/web_fetch", description="Répertoire temporaire de sortie")
    mode: str       = Field("pdf", description="pdf | html")
    parser: str     = Field("docling", description="docling | mineru | simple")
    strategy: str   = Field("by_token", description="by_token | by_sentence | by_block")
    entity: Optional[str]        = Field(None, description="Entité propriétaire")
    validity_date: Optional[str] = Field(None, description="Date de validité ISO YYYY-MM-DD")


class CrawlSharepointRequest(BaseModel):
    site_url: Optional[str]  = Field(None, description="URL complète du site SharePoint")
    site_name: Optional[str] = Field(None, description="Nom court du site (alternatif à site_url)")
    folder_path: Optional[str] = Field(None, description="Sous-dossier à indexer (None = racine)")
    output_dir: str  = Field("./tmp/sharepoint_fetch", description="Répertoire de téléchargement")
    parser: str      = Field("docling", description="docling | mineru | simple")
    strategy: str    = Field("by_token", description="by_token | by_sentence | by_block")
    # Credentials optionnels — sinon lus depuis les variables d'environnement
    client_id: Optional[str]     = Field(None, description="App Registration client_id (Entra ID)")
    client_secret: Optional[str] = Field(None, description="App Registration client_secret")
    tenant_id: Optional[str]     = Field(None, description="Tenant ID Azure AD")
    entity: Optional[str]        = Field(None, description="Entité propriétaire")
    validity_date: Optional[str] = Field(None, description="Date de validité ISO YYYY-MM-DD")


class CrawlTaskItem(BaseModel):
    """Un document découvert et dispatché par un crawl."""
    object_key: str
    task_id: str
    source_label: str


class CrawlJobResponse(BaseModel):
    """Réponse d'un endpoint /connectors/* — résumé du crawl lancé."""
    crawl_task_id: str = Field(..., description="Identifiant de la tâche de crawl Celery")
    status: str        = Field("queued", description="queued — le crawl est en cours")
    connector: str     = Field(..., description="local | web | sharepoint")
    message: str       = Field("", description="Description de la demande")


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
    question_id: Optional[str] = Field(None, description="Identifiant unique de la question (UnifiedRAGState.question_id)")
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


# ── Sessions de chat ──────────────────────────────────────────────────────────

class SessionMessageItem(BaseModel):
    """Un message dans une session de chat."""
    id: str
    role: str  # "user" | "assistant"
    content: str
    sources: list[ChunkModel] = []
    follow_up_suggestions: list[str] = []
    created_at: str


class SessionItem(BaseModel):
    """Vue synthétique d'une session pour la liste."""
    id: str
    title: Optional[str] = None
    created_at: str
    updated_at: str
    message_count: int = 0
    last_message: Optional[str] = None


class SessionDetail(BaseModel):
    """Session complète avec tous ses messages."""
    id: str
    title: Optional[str] = None
    created_at: str
    updated_at: str
    messages: list[SessionMessageItem] = []


class RenameSessionRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
