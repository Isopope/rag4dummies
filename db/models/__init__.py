"""Package db.models — expose tous les modèles SQLAlchemy et la Base."""
from .base import Base
from .conversation import Conversation
from .document import Document, DocumentStatus
from .message import Message, ROLE_ASSISTANT, ROLE_USER
from .user import User

__all__ = [
    "Base",
    "Conversation",
    "Document",
    "DocumentStatus",
    "Message",
    "ROLE_ASSISTANT",
    "ROLE_USER",
    "User",
]
