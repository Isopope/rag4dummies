"""
Package storage — abstraction sur le stockage de documents (PDFs).

Deux implémentations :
- LocalDocumentStore  : fichiers locaux dans ./uploads/ (dev sans Docker)
- MinioDocumentStore  : bucket MinIO/S3 (dev Docker + production)

Le choix se fait à partir des variables d'environnement :
  - MINIO_ENDPOINT défini → MinioDocumentStore
  - sinon              → LocalDocumentStore
"""
from storage.document_store import DocumentStore, LocalDocumentStore, MinioDocumentStore, make_document_store

__all__ = ["DocumentStore", "LocalDocumentStore", "MinioDocumentStore", "make_document_store"]
