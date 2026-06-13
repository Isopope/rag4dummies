"""Package db.models — expose tous les modèles SQLAlchemy et la Base."""
from .base import Base
from .connector_config import ConnectorConfig, DEFAULT_SYNC_INTERVAL_SECONDS
from .conversation import Conversation
from .document import Document, DocumentStatus
from .entity import Entity
from .message import Message, ROLE_ASSISTANT, ROLE_USER
from .user import User

__all__ = [
    "Base",
    "ConnectorConfig",
    "DEFAULT_SYNC_INTERVAL_SECONDS",
    "Conversation",
    "Document",
    "DocumentStatus",
    "Entity",
    "Message",
    "ROLE_ASSISTANT",
    "ROLE_USER",
    "User",
]
