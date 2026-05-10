"""Router /evals — comparaisons entre moteurs agentiques."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from application import EvaluationService, ObservabilityService
from ..deps import get_agent_engine_for_model, get_observability_store
from ..models import EvalCompareRequest, EvalCompareResponse

router = APIRouter()


@router.post("/compare", response_model=EvalCompareResponse, summary="Comparer plusieurs moteurs")
async def compare_engines(
    body: EvalCompareRequest,
    observability_store=Depends(get_observability_store),
) -> EvalCompareResponse:
    evaluation_service = EvaluationService(
        engine_factory=lambda model, engine_id: get_agent_engine_for_model(model, engine_name=engine_id, surface="eval"),
        observability_service=ObservabilityService(observability_store),
        store=observability_store,
    )
    run = evaluation_service.compare(
        question=body.question,
        engines=body.engines,
        model=body.model,
        source_filter=body.source_filter,
        conversation_summary=body.conversation_summary,
        user_id=body.user_id,
        session_id=body.session_id,
        expected_answer=body.expected_answer,
        expected_sources=body.expected_sources,
        debug=body.debug,
    )
    return EvalCompareResponse(**run)


@router.get("/{eval_id}", response_model=EvalCompareResponse, summary="Détail d'un run d'évaluation")
async def get_eval_run(
    eval_id: str,
    observability_store=Depends(get_observability_store),
) -> EvalCompareResponse:
    run = observability_store.get_eval_run(eval_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run d'évaluation introuvable.")
    return EvalCompareResponse(**run)
