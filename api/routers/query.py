"""Router /query — requête RAG synchrone et streaming SSE."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from application import AgentService, ConversationService, ObservabilityService
from ..auth import current_active_user, current_optional_user
from ..deps import get_agent_engine_for_model, get_document_store, get_observability_store
from ..engine_selection import resolve_agent_engine_name
from ..models import BboxModel, ChunkModel, QueryRequest, QueryResponse, StreamEvent
from db import get_db_session
from db.models.user import User

router = APIRouter()


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


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    observability_store=Depends(get_observability_store),
) -> QueryResponse:
    engine_name = resolve_agent_engine_name(body.engine_id, surface="query")
    agent_service = AgentService(
        engine_factory=lambda model: get_agent_engine_for_model(model, engine_name=engine_name, surface="query"),
    )
    observability_service = ObservabilityService(observability_store)
    try:
        execution = await agent_service.execute_query(
            question=body.question,
            source_filter=body.source_filter,
            model=body.model,
            engine_id=engine_name,
        )
    except Exception as exc:
        logger.exception("Erreur query RAG : {}", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    sources = _add_pdf_urls(
        [_chunk_to_model(d) for d in execution.result.get("sources", [])],
        doc_store,
    )
    observability_service.record_trace(
        question=body.question,
        mode="query",
        engine_id=engine_name,
        model=body.model,
        source_filter=body.source_filter,
        conversation_summary=body.conversation_summary,
        session_id=body.session_id,
        user_id="anonymous",
        result=execution.result,
        usage=execution.usage,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
    )

    return QueryResponse(
        question_id             = execution.result.get("question_id", ""),
        question                = body.question,
        answer                  = execution.result.get("answer", ""),
        engine_id               = execution.result.get("engine_id", engine_name),
        sources                 = sources,
        follow_up_suggestions   = execution.result.get("follow_up_suggestions", []),
        conversation_title      = execution.result.get("conversation_title"),
        n_retrieved             = execution.result.get("n_retrieved", 0),
        decision_log            = execution.result.get("decision_log", []),
        usage                   = execution.usage,
        error                   = execution.result.get("error"),
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
    observability_store=Depends(get_observability_store),
    db_session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_optional_user),
):
    engine_name = resolve_agent_engine_name(body.engine_id, surface="query_stream")
    agent_service = AgentService(
        engine_factory=lambda model: get_agent_engine_for_model(model, engine_name=engine_name, surface="query_stream"),
    )
    conversation_service = ConversationService(db_session)
    observability_service = ObservabilityService(observability_store)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    agent_service.start_stream_query(
        question=body.question,
        source_filter=body.source_filter,
        conversation_summary=body.conversation_summary,
        model=body.model,
        engine_id=engine_name,
        queue=queue,
        loop=loop,
    )

    async def _event_generator() -> AsyncGenerator[str, None]:
        answer      = ""
        sources:    list[ChunkModel] = []
        follow_ups: list[str]        = []
        title:      str | None       = None
        question_id: str | None      = None
        usage_summary: dict | None   = None
        trace_meta: dict | None      = None
        trace_events: list[dict]     = []
        stream_error: str | None     = None
        max_iterations               = 0

        while True:
            event = await queue.get()

            if isinstance(event, dict) and "__trace__" in event:
                trace_meta = event["__trace__"]
                continue

            if isinstance(event, dict) and "__usage__" in event:
                usage_summary = event["__usage__"]
                continue

            # Erreur dans le thread producteur
            if isinstance(event, dict) and "__error__" in event:
                stream_error = event["__error__"]
                err_evt = StreamEvent(type="error", error=event["__error__"])
                yield f"data: {err_evt.model_dump_json()}\n\n"
                continue

            # Sentinelle de fin
            if event is None:
                # ── Auto-save session (uniquement si authentifié) ──────────────
                saved_session_id: str | None = body.session_id
                if user is not None:
                    try:
                        saved_session_id = await conversation_service.save_stream_turn(
                            requested_session_id=body.session_id,
                            user_id=str(user.id),
                            question=body.question,
                            answer=answer,
                            sources=[c.model_dump() for c in sources],
                            follow_up_suggestions=follow_ups,
                            question_id=question_id,
                            title=title,
                            usage=usage_summary,
                        )
                    except Exception as exc:
                        logger.warning("Auto-save session échoué : {}", exc)
                # ───────────────────────────────────────────────────────────────
                trace_record = observability_service.record_trace(
                    question=body.question,
                    mode="query_stream",
                    engine_id=engine_name,
                    model=body.model,
                    source_filter=body.source_filter,
                    conversation_summary=body.conversation_summary,
                    session_id=saved_session_id or body.session_id,
                    user_id=str(user.id) if user is not None else "anonymous",
                    result={
                        "question_id": question_id,
                        "trace_id": question_id,
                        "answer": answer,
                        "sources": [c.model_dump() for c in sources],
                        "follow_up_suggestions": follow_ups,
                        "conversation_title": title,
                        "n_retrieved": len(sources),
                        "iterations": max_iterations,
                        "stop_reason": "completed" if stream_error is None else "error",
                        "error": stream_error,
                    },
                    usage=usage_summary,
                    started_at=(trace_meta or {}).get("started_at", _utcnow_iso()),
                    completed_at=(trace_meta or {}).get("completed_at", _utcnow_iso()),
                    events=trace_events,
                    error=stream_error,
                    metadata={
                        "duration_ms": (trace_meta or {}).get("duration_ms"),
                        "event_count": (trace_meta or {}).get("event_count", len(trace_events)),
                    },
                )
                done_evt = StreamEvent(
                    type                  = "done",
                    answer                = answer,
                    engine_id             = engine_name,
                    sources               = sources,
                    follow_up_suggestions = follow_ups,
                    conversation_title    = title,
                    question_id           = question_id,
                    session_id            = saved_session_id,
                    usage                 = usage_summary,
                )
                if not question_id:
                    done_evt.question_id = trace_record["trace_id"]
                yield f"data: {done_evt.model_dump_json()}\n\n"
                break

            event_type = event.get("type", "node_update")
            message = event.get("message")
            node_name = event.get("node")
            payload = event.get("payload") or {}
            trace_events.append(
                {
                    "ts": event.get("ts", _utcnow_iso()),
                    "type": event_type,
                    "node": node_name,
                    "message": message,
                    "engine_id": event.get("engine_id", engine_name),
                }
            )
            max_iterations = max(max_iterations, int(payload.get("agent_iterations", 0) or 0))

            evt = StreamEvent(
                type="answer" if event_type == "answer_completed" else "node_update",
                node=node_name,
                message=message,
                engine_id=event.get("engine_id", engine_name),
            )

            raw_sources = event.get("sources") or payload.get("reranked_docs") or []
            if raw_sources:
                sources = _add_pdf_urls(
                    [_chunk_to_model(d) for d in raw_sources],
                    doc_store,
                )
                evt.sources = sources

            if event.get("answer"):
                answer = event["answer"]
                evt.answer = answer

            if event.get("follow_up_suggestions"):
                follow_ups = event["follow_up_suggestions"]
                evt.follow_up_suggestions = follow_ups

            if event.get("conversation_title"):
                title = event["conversation_title"]
                evt.conversation_title = title

            if event.get("question_id"):
                question_id = event["question_id"]

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
