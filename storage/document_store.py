"""
Abstraction de stockage de documents (PDFs).

Deux backends :
- LocalDocumentStore  : stockage local sur disque (./uploads/) — dev sans Docker
- MinioDocumentStore  : bucket MinIO / S3-compatible — dev Docker + production

Interface commune :
    upload(file_bytes, object_key, content_type) -> object_key
    presigned_url(object_key, expires_seconds)  -> str (URL)
    delete(object_key)                          -> None
    exists(object_key)                          -> bool

Choix du backend via `make_document_store()` : si MINIO_ENDPOINT est défini dans
l'environnement, on utilise MinioDocumentStore ; sinon LocalDocumentStore.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path

from loguru import logger


# ---------------------------------------------------------------------------
# Interface abstraite
# ---------------------------------------------------------------------------

class DocumentStore(ABC):
    """Interface de stockage de documents."""

    @abstractmethod
    def upload(self, file_bytes: bytes, object_key: str, content_type: str = "application/pdf") -> str:
        """
        Stocke le fichier et retourne la clé de l'objet (object_key inchangé).
        """

    @abstractmethod
    def presigned_url(self, object_key: str, expires_seconds: int = 3600) -> str:
        """Retourne une URL valide pour télécharger le fichier directement."""

    @abstractmethod
    def delete(self, object_key: str) -> None:
        """Supprime un fichier du store."""

    @abstractmethod
    def download(self, object_key: str) -> bytes:
        """Télécharge un fichier et retourne son contenu en bytes."""

    @abstractmethod
    def exists(self, object_key: str) -> bool:
        """Vérifie si un fichier existe dans le store."""

    # ------------------------------------------------------------------
    # Utilitaire partagé : génère une clé déterministe sans collision
    # ------------------------------------------------------------------
    @staticmethod
    def make_object_key(filename: str, file_bytes: bytes) -> str:
        """
        Génère une clé MinIO/locale stable : ``{sha256_8chars}-{safe_name}.pdf``
        
        - Préfixe de 8 caractères du SHA-256 du contenu → évite les collisions
          entre fichiers différents ayant le même nom.
        - Nom nettoyé : espaces → tirets, caractères non-ASCII supprimés.
        """
        sha_prefix = hashlib.sha256(file_bytes).hexdigest()[:8]
        safe = re.sub(r"[^\w.\-]", "-", Path(filename).stem, flags=re.ASCII)
        safe = re.sub(r"-{2,}", "-", safe).strip("-").lower() or "document"
        return f"{sha_prefix}-{safe}.pdf"


# ---------------------------------------------------------------------------
# Backend local (fallback dev)
# ---------------------------------------------------------------------------

class LocalDocumentStore(DocumentStore):
    """
    Stockage local dans un répertoire ``uploads/`` à la racine du projet.
    Les URLs retournées pointent vers l'endpoint FastAPI ``GET /documents/{key}``.
    """

    def __init__(self, uploads_dir: Path | str | None = None, base_url: str = "http://localhost:8000") -> None:
        self._dir = Path(uploads_dir) if uploads_dir else Path(__file__).parent.parent / "uploads"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._base_url = base_url.rstrip("/")
        logger.info("LocalDocumentStore initialisé → {}", self._dir)

    def upload(self, file_bytes: bytes, object_key: str, content_type: str = "application/pdf") -> str:
        dest = self._dir / object_key
        dest.write_bytes(file_bytes)
        logger.debug("LocalStore: fichier écrit → {}", dest)
        return object_key

    def presigned_url(self, object_key: str, expires_seconds: int = 3600) -> str:
        # Mode local : URL directe vers l'API (pas d'expiration réelle)
        return f"{self._base_url}/documents/{object_key}"

    def delete(self, object_key: str) -> None:
        path = self._dir / object_key
        if path.exists():
            path.unlink()
            logger.debug("LocalStore: supprimé → {}", path)

    def download(self, object_key: str) -> bytes:
        path = self._dir / object_key
        if not path.is_file():
            raise FileNotFoundError(f"LocalStore: fichier introuvable → {path}")
        return path.read_bytes()

    def exists(self, object_key: str) -> bool:
        return (self._dir / object_key).is_file()

    @property
    def uploads_dir(self) -> Path:
        return self._dir


# ---------------------------------------------------------------------------
# Backend MinIO / S3-compatible
# ---------------------------------------------------------------------------

class MinioDocumentStore(DocumentStore):
    """
    Stockage dans un bucket MinIO (ou tout service S3-compatible).

    Variables d'environnement attendues :
        MINIO_ENDPOINT          ex. localhost:9000
        MINIO_ACCESS_KEY        ex. minioadmin
        MINIO_SECRET_KEY        ex. minioadmin
        MINIO_BUCKET            ex. rag-documents
        MINIO_SECURE            true | false  (HTTPS ?)
        MINIO_PRESIGN_EXPIRES   secondes (défaut 3600)
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
    ) -> None:
        try:
            from minio import Minio  # import paresseux — SDK optionnel
        except ImportError as exc:
            raise ImportError(
                "Le package 'minio' est requis pour MinioDocumentStore. "
                "Installez-le avec : pip install minio>=7.2"
            ) from exc

        self._client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        self._bucket = bucket
        self._ensure_bucket()
        logger.info("MinioDocumentStore initialisé → endpoint={} bucket={}", endpoint, bucket)

    # ------------------------------------------------------------------
    def _ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)
            logger.info("MinIO: bucket '{}' créé", self._bucket)

    # ------------------------------------------------------------------
    def upload(self, file_bytes: bytes, object_key: str, content_type: str = "application/pdf") -> str:
        self._client.put_object(
            self._bucket,
            object_key,
            io.BytesIO(file_bytes),
            length=len(file_bytes),
            content_type=content_type,
        )
        logger.debug("MinIO: uploadé → {}/{}", self._bucket, object_key)
        return object_key

    def presigned_url(self, object_key: str, expires_seconds: int = 3600) -> str:
        url = self._client.presigned_get_object(
            self._bucket,
            object_key,
            expires=timedelta(seconds=expires_seconds),
        )
        return url

    def delete(self, object_key: str) -> None:
        self._client.remove_object(self._bucket, object_key)
        logger.debug("MinIO: supprimé → {}/{}", self._bucket, object_key)

    def download(self, object_key: str) -> bytes:
        response = self._client.get_object(self._bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def exists(self, object_key: str) -> bool:
        try:
            self._client.stat_object(self._bucket, object_key)
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Fabrique — choisit le backend selon les variables d'environnement
# ---------------------------------------------------------------------------

def make_document_store() -> DocumentStore:
    """
    Retourne le DocumentStore approprié selon la configuration :

    - Si ``MINIO_ENDPOINT`` est défini → MinioDocumentStore
    - Sinon                            → LocalDocumentStore (fallback)
    """
    endpoint = os.getenv("MINIO_ENDPOINT", "").strip()
    if endpoint:
        return MinioDocumentStore(
            endpoint=endpoint,
            access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
            bucket=os.getenv("MINIO_BUCKET", "rag-documents"),
            secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
        )

    logger.warning(
        "MINIO_ENDPOINT non défini — stockage local activé (./uploads/). "
        "Configurez MinIO pour la production."
    )
    base_url = os.getenv("API_BASE_URL", "http://localhost:8000")
    return LocalDocumentStore(base_url=base_url)
