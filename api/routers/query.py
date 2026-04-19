"""Router /query — requête RAG synchrone et streaming SSE."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from loguru import logger

from ..deps import get_agent
from ..models import ChunkModel, QueryRequest, QueryResponse, StreamEvent

router = APIRouter()

_THREAD_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="rag-query")


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
    )


# ── POST /query — synchrone ────────────────────────────────────────────────────

@router.post(
    "",
    response_model=QueryResponse,
    summary="Requête RAG (synchrone)",
    description="Exécute le pipeline RAG complet et retourne la réponse finale.",
)
async def query(
    body: QueryRequest,
    agent=Depends(get_agent),
) -> QueryResponse:
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            _THREAD_POOL,
            lambda: agent.query(question=body.question, source=body.source_filter),
        )
    except Exception as exc:
        logger.exception("Erreur query RAG : {}", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    return QueryResponse(
        question_id             = result.get("question_id", ""),
        question                = body.question,
        answer                  = result.get("answer", ""),
        sources                 = [_chunk_to_model(d) for d in result.get("sources", [])],
        follow_up_suggestions   = result.get("follow_up_suggestions", []),
        conversation_title      = result.get("conversation_title"),
        n_retrieved             = result.get("n_retrieved", 0),
        decision_log            = result.get("decision_log", []),
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
    agent=Depends(get_agent),
):
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _producer():
        """Exécute stream_query dans un thread et empile les événements dans la queue."""
        try:
            for event in agent.stream_query(
                question             = body.question,
                source               = body.source_filter,
                conversation_summary = body.conversation_summary,
            ):
                loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, {"__error__": str(exc)})
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinelle

    loop.run_in_executor(_THREAD_POOL, _producer)

    async def _event_generator() -> AsyncGenerator[str, None]:
        answer     = ""
        sources:   list[ChunkModel] = []
        follow_ups: list[str]       = []
        title:     str | None       = None

        while True:
            event = await queue.get()

            # Erreur dans le thread producteur
            if isinstance(event, dict) and "__error__" in event:
                err_evt = StreamEvent(type="error", error=event["__error__"])
                yield f"data: {err_evt.model_dump_json()}\n\n"
                break

            # Sentinelle de fin
            if event is None:
                done_evt = StreamEvent(
                    type                  = "done",
                    answer                = answer,
                    sources               = sources,
                    follow_up_suggestions = follow_ups,
                    conversation_title    = title,
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

                if "reranked_docs" in state_update:
                    sources      = [_chunk_to_model(d) for d in state_update["reranked_docs"]]
                    evt.sources  = sources

                if "follow_up_suggestions" in state_update:
                    follow_ups               = state_update["follow_up_suggestions"]
                    evt.follow_up_suggestions = follow_ups

                if "conversation_title" in state_update:
                    title                = state_update["conversation_title"]
                    evt.conversation_title = title

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
