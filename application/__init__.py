"""Services applicatifs extraits des couches API/worker."""

__all__ = [
    "AgentExecutionResult",
    "AgentService",
    "ConversationService",
    "IngestionService",
    "ObservabilityService",
    "EvaluationService",
]


def __getattr__(name: str):
    if name in {"AgentExecutionResult", "AgentService"}:
        from .agent_service import AgentExecutionResult, AgentService

        return {"AgentExecutionResult": AgentExecutionResult, "AgentService": AgentService}[name]
    if name == "ConversationService":
        from .conversation_service import ConversationService

        return ConversationService
    if name == "IngestionService":
        from .ingestion_service import IngestionService

        return IngestionService
    if name == "ObservabilityService":
        from .observability_service import ObservabilityService

        return ObservabilityService
    if name == "EvaluationService":
        from .evaluation_service import EvaluationService

        return EvaluationService
    raise AttributeError(name)
