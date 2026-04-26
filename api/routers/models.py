"""Router /models — liste les modèles LLM disponibles via LiteLLM."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from llm.constants import PROVIDER_MODELS
from rag_agent.config import RAGConfig

router = APIRouter()


class ModelInfo(BaseModel):
    id: str
    label: str
    provider: str


class ModelsResponse(BaseModel):
    models: list[ModelInfo]
    default: str


def _make_label(model_id: str) -> str:
    """Génère un label lisible depuis l'identifiant LiteLLM."""
    # Retire le préfixe provider/ (ex: "mistral/mistral-large-latest" → "mistral-large-latest")
    name = model_id.split("/")[-1]
    # CamelCase / tirets → lisible
    return name.replace("-", " ").replace("_", " ").title()


@router.get("", response_model=ModelsResponse, summary="Modèles LLM disponibles")
async def list_models() -> ModelsResponse:
    """Retourne la liste des modèles définis dans llm/constants.py, groupés par provider."""
    default_model = RAGConfig.from_env().llm_model

    models: list[ModelInfo] = []
    for provider, ids in PROVIDER_MODELS.items():
        for model_id in ids:
            models.append(ModelInfo(
                id=model_id,
                label=_make_label(model_id),
                provider=provider,
            ))

    return ModelsResponse(models=models, default=default_model)
