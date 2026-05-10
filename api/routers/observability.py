"""Router /observability — lecture des traces d'execution."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from application import ObservabilityService
from ..deps import get_observability_store
from ..models import TraceDetail, TraceItem, TraceSummaryResponse

router = APIRouter()


@router.get("/summary", response_model=TraceSummaryResponse, summary="Résumé agrégé des traces")
async def get_summary(
    limit: int = Query(100, ge=1, le=1000),
    observability_store=Depends(get_observability_store),
) -> TraceSummaryResponse:
    service = ObservabilityService(observability_store)
    return TraceSummaryResponse(**service.summarize_traces(limit=limit))


@router.get("/traces", response_model=list[TraceItem], summary="Lister les traces récentes")
async def list_traces(
    limit: int = Query(20, ge=1, le=200),
    engine_id: str | None = Query(None),
    mode: str | None = Query(None),
    observability_store=Depends(get_observability_store),
) -> list[TraceItem]:
    service = ObservabilityService(observability_store)
    traces = service.list_traces(limit=limit, engine_id=engine_id, mode=mode)
    return [TraceItem(**trace) for trace in traces]


@router.get("/traces/{trace_id}", response_model=TraceDetail, summary="Détail d'une trace")
async def get_trace(
    trace_id: str,
    observability_store=Depends(get_observability_store),
) -> TraceDetail:
    service = ObservabilityService(observability_store)
    trace = service.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace introuvable.")
    return TraceDetail(**trace)
