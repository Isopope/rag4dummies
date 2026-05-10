"""Router /engines — liste les moteurs agentiques disponibles."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..engine_selection import get_default_agent_engine_name, list_agent_engines

router = APIRouter()


class AgentEngineInfo(BaseModel):
    id: str
    label: str


class AgentEnginesResponse(BaseModel):
    engines: list[AgentEngineInfo]
    default_query: str
    default_stream: str


ENGINE_LABELS = {
    "legacy_langgraph": "Legacy LangGraph",
    "react_runtime_v2": "React Runtime V2",
}


@router.get("", response_model=AgentEnginesResponse, summary="Moteurs agentiques disponibles")
async def list_engines() -> AgentEnginesResponse:
    engines = [
        AgentEngineInfo(id=engine_id, label=ENGINE_LABELS.get(engine_id, engine_id))
        for engine_id in list_agent_engines()
    ]
    return AgentEnginesResponse(
        engines=engines,
        default_query=get_default_agent_engine_name("query"),
        default_stream=get_default_agent_engine_name("query_stream"),
    )
