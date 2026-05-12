"""Router /query — requête RAG synchrone et streaming SSE."""
from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_active_user, current_optional_user
from ..deps import get_agent_for_model, get_document_store
from ..models import BboxModel, ChunkModel, CitationInfoModel, QueryRequest, QueryResponse, StreamEvent
from db import get_db_session
from db.models.user import User
from db.repositories import ConversationRepository
from llm.usage import track_usage
from rag_agent.utils.citations import hyperlink_citations, CitationInfo

router = APIRouter()

_THREAD_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="rag-query")


def _parse_bboxes(raw: str | None) -> list[BboxModel]:
    """Désérialise bboxes_json → list[BboxModel].

    Format attendu : [[page, x0, y0, x1, y1], ...]
    Tolère les valeurs None / malformées (renvoie [] silencieusement).
    """
    if not raw:
        return []
    try:
        entries = json.loads(raw)
        return [
            BboxModel(page=b[0], x0=b[1], y0=b[2], x1=b[3], y1=b[4])
            for b in entries
            if isinstance(b, (list, tuple)) and len(b) == 5
        ]
    except (json.JSONDecodeError, (IndexError, TypeError)):
        return []


def _chunk_to_model(doc: dict) -> ChunkModel:
    return ChunkModel(
        source       = doc.get("source", ""),
        page_content = doc.get("page_content", ""),
        page_idx     = doc.get("page_idx", 0),
        kind         = doc.get("kind", "text"),
        title_path   = doc.get("title_path", ""),
        chunk_index  = doc.get("chunk_index", 0),
        rerank_score = doc.get("_rerank_score"),
        score        = doc.get("_score"),
        bboxes       = _parse_bboxes(doc.get("bboxes_json")),
    )


def _add_pdf_urls(chunks: list[ChunkModel], doc_store, expires_seconds: int = 3600) -> list[ChunkModel]:
    """Génère une presigned URL par source unique et l'affecte à chaque chunk.

    Silencieux en cas d'erreur (MinIO indisponible → pdf_url reste None).
    """
    import os
    expires = int(os.getenv("MINIO_PRESIGN_EXPIRES", str(expires_seconds)))
    url_cache: dict[str, str] = {}
    for chunk in chunks:
        source = chunk.source
        if not source:
            continue
        if source not in url_cache:
            try:
                url_cache[source] = doc_store.presigned_url(source, expires_seconds=expires)
            except Exception as exc:
                logger.warning("Impossible de générer la presigned URL pour '{}' : {}", source, exc)
                url_cache[source] = ""
        if url_cache[source]:
            chunk.pdf_url = url_cache[source]
    return chunks


# ── POST /query — synchrone ────────────────────────────────────────────────────

@router.post(
    "",
    response_model=QueryResponse,
    summary="Requête RAG (synchrone)",
    description="Exécute le pipeline RAG complet et retourne la réponse finale.",
)
async def query(
    body: QueryRequest,
    doc_store=Depends(get_document_store),
) -> QueryResponse:
    agent = get_agent_for_model(body.model)
    loop = asyncio.get_event_loop()

    def _run_query():
        with track_usage() as tracker:
            result = agent.query(question=body.question, source=body.source_filter)
        return result, tracker.snapshot()

    try:
        result, usage = await loop.run_in_executor(
            _THREAD_POOL,
            _run_query,
        )
    except Exception as exc:
        logger.exception("Erreur query RAG : {}", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    sources = _add_pdf_urls(
        [_chunk_to_model(d) for d in result.get("sources", [])],
        doc_store,
    )

    return QueryResponse(
        question_id             = result.get("question_id", ""),
        question                = body.question,
        answer                  = result.get("answer", ""),
        sources                 = sources,
        follow_up_suggestions   = result.get("follow_up_suggestions", []),
        conversation_title      = result.get("conversation_title"),
        n_retrieved             = result.get("n_retrieved", 0),
        decision_log            = result.get("decision_log", []),
        usage                   = usage,
        error                   = result.get("error"),
    )


# ── POST /query/stream — SSE ───────────────────────────────────────────────────

@router.post(
    "/stream",
    summary="Requête RAG (streaming SSE)",
    description=(
        "Exécute le pipeline RAG et émet les événements nœud par nœud via Server-Sent Events.\n\n"
        "Chaque événement est une ligne `data: <JSON>\\n\\n`.\n"
        "Le type `done` est l'événement terminal contenant la réponse complète."
    ),
    response_class=StreamingResponse,
)
async def query_stream(
    body: QueryRequest,
    doc_store=Depends(get_document_store),
    db_session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_optional_user),
):
    agent = get_agent_for_model(body.model)
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _producer():
        """Exécute stream_query dans un thread et empile les événements dans la queue."""
        tracker = None
        try:
            with track_usage() as current_tracker:
                tracker = current_tracker
                for event in agent.stream_query(
                    question             = body.question,
                    source               = body.source_filter,
                    conversation_summary = body.conversation_summary,
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, {"__error__": str(exc)})
        finally:
            if tracker is not None:
                loop.call_soon_threadsafe(queue.put_nowait, {"__usage__": tracker.snapshot()})
            loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinelle

    loop.run_in_executor(_THREAD_POOL, _producer)

    async def _event_generator() -> AsyncGenerator[str, None]:
        answer      = ""
        sources:    list[ChunkModel] = []
        follow_ups: list[str]        = []
        title:      str | None       = None
        question_id: str | None      = None
        usage_summary: dict | None   = None
        raw_citation_infos: list[dict] = []

        while True:
            event = await queue.get()

            if isinstance(event, dict) and "__usage__" in event:
                usage_summary = event["__usage__"]
                continue

            # Erreur dans le thread producteur
            if isinstance(event, dict) and "__error__" in event:
                err_evt = StreamEvent(type="error", error=event["__error__"])
                yield f"data: {err_evt.model_dump_json()}\n\n"
                break

            # Sentinelle de fin
            if event is None:
                # ── Auto-save session (uniquement si authentifié) ──────────────
                saved_session_id: str | None = body.session_id
                if user is not None:
                    try:
                        repo = ConversationRepository(db_session)
                        if saved_session_id:
                            # Vérifier que la session appartient bien à l'utilisateur
                            import uuid as _uuid
                            existing = await repo.get(_uuid.UUID(saved_session_id))
                            if existing is None or existing.user_id != str(user.id):
                                saved_session_id = None  # session invalide → créer une nouvelle
                        if saved_session_id:
                            await repo.append_turn(
                                session_id            = saved_session_id,
                                question              = body.question,
                                answer                = answer,
                                sources               = [c.model_dump() for c in sources],
                                follow_up_suggestions = follow_ups,
                                n_retrieved           = len(sources),
                                question_id           = question_id,
                                title                 = title,
                                usage                 = usage_summary,
                            )
                        else:
                            conv = await repo.create_session(user_id=str(user.id), title=title)
                            saved_session_id = str(conv.id)
                            await repo.append_turn(
                                session_id            = saved_session_id,
                                question              = body.question,
                                answer                = answer,
                                sources               = [c.model_dump() for c in sources],
                                follow_up_suggestions = follow_ups,
                                n_retrieved           = len(sources),
                                question_id           = question_id,
                                usage                 = usage_summary,
                            )
                        await db_session.commit()
                    except Exception as exc:
                        logger.warning("Auto-save session échoué : {}", exc)
                # ───────────────────────────────────────────────────────────────
                # Applique les hyperliens [[N]](url) sur la réponse finale
                url_map = {c.source: c.pdf_url for c in sources if c.pdf_url}
                citation_infos_objs = [
                    CitationInfo(
                        citation_number = ci["citation_number"],
                        document_id     = ci["document_id"],
                        source          = ci["source"],
                        page_idx        = ci.get("page_idx", 0),
                        title_path      = ci.get("title_path", ""),
                    )
                    for ci in raw_citation_infos
                ]
                answer_hl = hyperlink_citations(answer, citation_infos_objs, url_map)
                citation_models = [
                    CitationInfoModel(**ci) for ci in raw_citation_infos
                ]
                done_evt = StreamEvent(
                    type                  = "done",
                    answer                = answer_hl,
                    sources               = sources,
                    citation_infos        = citation_models,
                    follow_up_suggestions = follow_ups,
                    conversation_title    = title,
                    question_id           = question_id,
                    session_id            = saved_session_id,
                    usage                 = usage_summary,
                )
                yield f"data: {done_evt.model_dump_json()}\n\n"
                break

            # Événement LangGraph : {node_name: state_update}
            for node_name, state_update in event.items():
                logs    = state_update.get("decision_log", [])
                message = logs[-1].get("message", "") if logs else ""

                evt = StreamEvent(
                    type    = "node_update",
                    node    = node_name,
                    message = message,
                )

                if state_update.get("answer"):
                    answer    = state_update["answer"]
                    evt.type  = "answer"
                    evt.answer = answer

                if "retrieved_docs" in state_update:
                    sources      = _add_pdf_urls(
                        [_chunk_to_model(d) for d in state_update["retrieved_docs"]],
                        doc_store,
                    )
                    evt.sources  = sources

                # cited_docs (sous-ensemble cité par le LLM) remplace retrieved_docs
                # dès que disponible.
                if state_update.get("cited_docs"):
                    sources     = _add_pdf_urls(
                        [_chunk_to_model(d) for d in state_update["cited_docs"]],
                        doc_store,
                    )
                    evt.sources = sources

                # citation_infos est capturé pour la transformation hyperlink au done
                if state_update.get("citation_infos"):
                    raw_citation_infos = state_update["citation_infos"]

                if "follow_up_suggestions" in state_update:
                    follow_ups               = state_update["follow_up_suggestions"]
                    evt.follow_up_suggestions = follow_ups

                if "conversation_title" in state_update:
                    title                = state_update["conversation_title"]
                    evt.conversation_title = title

                if "question_id" in state_update and state_update["question_id"]:
                    question_id = state_update["question_id"]

                yield f"data: {evt.model_dump_json()}\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":       "keep-alive",
        },
    )
