"""Weaviate vector store — wrapper minimaliste pour le POC RAG.

Collection unique : RagChunk
Vectorizer       : NAMED VECTOR (vecteurs pré-calculés fournis à l'insertion)
Index            : HNSW cosinus + BM25 (activé par défaut sur les propriétés TEXT)
Recherche        : hybrid (BM25 + dense), paramétrable via alpha
"""
from __future__ import annotations

from loguru import logger

import weaviate
from weaviate.classes.config import (
    Configure,
    DataType,
    Property,
    Reconfigure,
    Tokenization,
    VectorDistances,
)
from weaviate.classes.query import Filter, HybridFusion, MetadataQuery

COLLECTION_NAME = "RagChunk"
CONTENT_VECTOR="content_vector"
TITLE_VECTOR="title_vector"


class WeaviateStore:
    """Client Weaviate encapsulant les opérations CRUD pour les RagChunks."""

    def __init__(self, host: str = "localhost", port: int = 8080) -> None:
        self._host = host
        self._port = port
        self._client: weaviate.WeaviateClient | None = None

    # ── connexion ─────────────────────────────────────────────────────────────

    def connect(self) -> None:
        self._client = weaviate.connect_to_local(host=self._host, port=self._port)
        logger.info("Connecté à Weaviate sur {}:{}", self._host, self._port)
        self._ensure_schema()

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    def is_ready(self) -> bool:
        try:
            return self._client is not None and self._client.is_ready()
        except Exception:
            return False

    def _ensure_connected(self) -> None:
        """Reconnecte automatiquement si la connexion Weaviate est perdue."""
        try:
            if self._client and self._client.is_ready():
                return
        except Exception:
            pass
        logger.warning("Connexion Weaviate perdue — reconnexion sur {}:{}", self._host, self._port)
        try:
            if self._client:
                try:
                    self._client.close()
                except Exception:
                    pass
            self._client = weaviate.connect_to_local(host=self._host, port=self._port)
            logger.info("Reconnexion Weaviate réussie.")
        except Exception as exc:
            raise RuntimeError(f"Impossible de se reconnecter à Weaviate : {exc}") from exc

    # ── schéma ────────────────────────────────────────────────────────────────

    def _ensure_schema(self) -> None:
        if self._client.collections.exists(COLLECTION_NAME):
            logger.debug("Collection {} déjà présente.", COLLECTION_NAME)
            self._migrate_schema()
            return

        self._client.collections.create(
            name=COLLECTION_NAME,
            vectorizer_config=[
                Configure.NamedVectors.none(
                    name=CONTENT_VECTOR,
                    vector_index_config=Configure.VectorIndex.hnsw(
                        distance_metric=VectorDistances.COSINE
                    ),
                ),
                Configure.NamedVectors.none(
                    name=TITLE_VECTOR,
                    vector_index_config=Configure.VectorIndex.hnsw(
                        distance_metric=VectorDistances.COSINE
                    ),
                ),
            ],
            inverted_index_config=Configure.inverted_index(
                index_null_state=True,
                index_property_length=True,
            ),
            properties=[
                # ── champs indexés BM25 (Tokenization.WORD) ───────────────
                Property(
                    name="page_content",
                    data_type=DataType.TEXT,
                    tokenization=Tokenization.WORD,
                ),
                Property(
                    name="title_path",
                    data_type=DataType.TEXT,
                    tokenization=Tokenization.WORD,
                ),
                Property(
                    name="title_text",
                    data_type=DataType.TEXT,
                    tokenization=Tokenization.WORD,
                ),
                Property(
                    name="doc_summary",
                    data_type=DataType.TEXT,
                    tokenization=Tokenization.WORD,
                ),
                Property(
                    name="chunk_context",
                    data_type=DataType.TEXT,
                    tokenization=Tokenization.WORD,
                ),
                Property(
                    name="metadata_suffix_keyword",
                    data_type=DataType.TEXT,
                    tokenization=Tokenization.WORD,
                ),
                # contenu enrichis pas de BM25 ACTIF
                Property(
                    name="embedding_content",
                    data_type=DataType.TEXT,
                    index_searchable=False,
                    skip_vectorization=True,
                ),
                Property(
                    name="title_prefix",
                    data_type=DataType.TEXT,
                    index_searchable=False,
                    skip_vectorization=True,
                ),
                Property(
                    name="metadata_suffix_semantic",
                    data_type=DataType.TEXT,
                    index_searchable=False,
                    skip_vectorization=True,
                ),
                # ── métadonnées structurelles (filtrage / affichage) ──────
                Property(name="source",        data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="kind",          data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="chunk_index",   data_type=DataType.INT),
                Property(name="page_idx",      data_type=DataType.INT),
                Property(name="token_count",   data_type=DataType.INT),
                Property(name="title_level",   data_type=DataType.INT),
                Property(name="reading_order", data_type=DataType.INT),
                Property(name="prev_chunk",    data_type=DataType.INT),
                Property(name="next_chunk",    data_type=DataType.INT),
                # ── contenus enrichis (pas de BM25 — markup/JSON) ─────────
                Property(
                    name="html",
                    data_type=DataType.TEXT,
                    index_searchable=False,
                    skip_vectorization=True,
                ),
                Property(
                    name="captions_json",
                    data_type=DataType.TEXT,
                    index_searchable=False,
                    skip_vectorization=True,
                ),
                Property(
                    name="footnotes_json",
                    data_type=DataType.TEXT,
                    index_searchable=False,
                    skip_vectorization=True,
                ),
                # ── coordonnées de localisation dans le PDF (visual grounding) ─
                # Format JSON : [[page, x0, y0, x1, y1], ...]  (points PDF, origine haut-gauche)
                Property(
                    name="bboxes_json",
                    data_type=DataType.TEXT,
                    index_searchable=False,
                    skip_vectorization=True,
                ),
                # ── métadonnées métier ─────────────────────────────────────
                Property(name="entity",        data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="validity_date", data_type=DataType.DATE, skip_vectorization=True),
                Property(name="embedding_model", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="embedding_provider", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="embedding_dim", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="embedding_version", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="embedding_created_at", data_type=DataType.DATE, skip_vectorization=True)
            ],
        )
        logger.info("Collection {} créée.", COLLECTION_NAME)

    def _migrate_schema(self) -> None:
        """Ajoute les propriétés manquantes à une collection existante (migration non-destructive)."""
        collection = self._client.collections.get(COLLECTION_NAME)
        cfg = collection.config.get()
        inv = cfg.inverted_index_config
        if not getattr(inv, "index_null_state", False):
            collection.config.update(
                inverted_index_config=Reconfigure.inverted_index(
                    index_null_state=True,
                    index_property_length=True,
                )
            )
            logger.info("invertedIndexConfig mis à jour (indexNullState=true) sur {}.", COLLECTION_NAME)
        existing_props = {p.name for p in cfg.properties}
        additions = [
            ("bboxes_json", Property(name="bboxes_json", data_type=DataType.TEXT, index_searchable=False, skip_vectorization=True)),
            ("entity", Property(name="entity", data_type=DataType.TEXT, skip_vectorization=True)),
            ("validity_date", Property(name="validity_date", data_type=DataType.DATE, skip_vectorization=True)),
            ("title_text", Property(name="title_text", data_type=DataType.TEXT, tokenization=Tokenization.WORD)),
            ("title_prefix", Property(name="title_prefix", data_type=DataType.TEXT, index_searchable=False, skip_vectorization=True)),
            ("doc_summary", Property(name="doc_summary", data_type=DataType.TEXT, tokenization=Tokenization.WORD)),
            ("chunk_context", Property(name="chunk_context", data_type=DataType.TEXT, tokenization=Tokenization.WORD)),
            ("embedding_content", Property(name="embedding_content", data_type=DataType.TEXT, index_searchable=False, skip_vectorization=True)),
            ("metadata_suffix_keyword", Property(name="metadata_suffix_keyword", data_type=DataType.TEXT, tokenization=Tokenization.WORD)),
            ("metadata_suffix_semantic", Property(name="metadata_suffix_semantic", data_type=DataType.TEXT, index_searchable=False, skip_vectorization=True)),
            ("embedding_model", Property(name="embedding_model", data_type=DataType.TEXT, skip_vectorization=True)),
            ("embedding_provider", Property(name="embedding_provider", data_type=DataType.TEXT, skip_vectorization=True)),
            ("embedding_dim", Property(name="embedding_dim", data_type=DataType.INT)),
            ("embedding_version", Property(name="embedding_version", data_type=DataType.TEXT, skip_vectorization=True)),
            ("embedding_created_at", Property(name="embedding_created_at", data_type=DataType.DATE, skip_vectorization=True)),
        ]
        for name, prop in additions:
            if name not in existing_props:
                collection.config.add_property(prop)
                logger.info("Propriété {} ajoutée à {}.", name, COLLECTION_NAME)
    def reset_collection(self) -> None:
        """Supprime et recrée la collection (dev / tests)."""
        if self._client.collections.exists(COLLECTION_NAME):
            self._client.collections.delete(COLLECTION_NAME)
            logger.warning("Collection {} supprimée.", COLLECTION_NAME)
        self._ensure_schema()

    # ── écriture ──────────────────────────────────────────────────────────────

    def insert_chunks(
        self,
        chunks: list[dict],
        vectors: list[list[float]],
        title_vectors: list[list[float]] | None = None,
    ) -> int:
        """Insère des chunks avec leurs vecteurs dans Weaviate.
        Parameters
        ----------
        chunks:
            Liste de dictionnaires représentant les propriétés de chaque chunk (doivent correspondre au schéma défini).
        vectors:
            Liste de vecteurs denses ('content_vector') un par chunk
        title_vectors:
            Liste de vecteurs denses ('title_vector') un par chunk (optionnel, peut être None si non utilisé)

        Returns le nombre d'objets insérés avec succès.
        """
        collection = self._client.collections.get(COLLECTION_NAME)
        inserted = 0
        failed = 0

        with collection.batch.dynamic() as batch:
            for i, (chunk, cv) in enumerate(zip(chunks, vectors)):
                named = {CONTENT_VECTOR: cv}
                if title_vectors and i < len(title_vectors):
                    named[TITLE_VECTOR] = title_vectors[i]
                batch.add_object(properties=chunk, vector=named)
                inserted += 1

        if hasattr(batch, "number_errors") and batch.number_errors:
            failed = batch.number_errors
            logger.warning("{} erreurs lors de l'insertion.", failed)

        logger.info("Inséré {} chunk(s) dans Weaviate.", inserted - failed)
        return inserted - failed

    def delete_source(self, source: str) -> int:
        """Supprime tous les chunks associés à une source donnée."""
        collection = self._client.collections.get(COLLECTION_NAME)
        result = collection.data.delete_many(
            where=Filter.by_property("source").equal(source)
        )
        count = result.successful if result is not None else 0
        logger.info("Supprimé {} chunk(s) pour la source : {}", count, source)
        return count

    # ── lecture ───────────────────────────────────────────────────────────────

    def hybrid_search(
        self,
        query: str,
        query_vector: list[float],
        top_k: int = 20,
        alpha: float = 0.5,
        source: str | None = None,
        target_vector: str = CONTENT_VECTOR,
    ) -> list[dict]:
        """Recherche hybride BM25 + dense (HNSW).

        Parameters
        ----------
        query:
            Texte brut de la question (utilisé par BM25).
        query_vector:
            Vecteur dense de la question.
        top_k:
            Nombre de résultats à retourner.
        alpha:
            Pondération : 0.0 = BM25 pur, 1.0 = dense pur.
        source:
            Filtre optionnel sur le chemin absolu du document.
        target_vector:
            Named vector cible (CONTENT_VECTOR ou TITLE_VECTOR).
        """
        from datetime import datetime, timezone
        self._ensure_connected()
        collection = self._client.collections.get(COLLECTION_NAME)

        today_rfc3339 = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
        validity_filter = (
            Filter.by_property("validity_date").is_none(True)
            | Filter.by_property("validity_date").greater_or_equal(today_rfc3339)
        )
        if source:
            filters = Filter.by_property("source").equal(source) & validity_filter
        else:
            filters = validity_filter

        result = collection.query.hybrid(
            query=query,
            vector=query_vector,
            alpha=alpha,
            limit=top_k,
            fusion_type=HybridFusion.RELATIVE_SCORE,
            return_metadata=MetadataQuery(score=True, explain_score=False),
            filters=filters,
            target_vector=target_vector,
        )

        docs = []
        for obj in result.objects:
            docs.append({
                **obj.properties,
                "_score": obj.metadata.score,
                "_id": str(obj.uuid),
            })
        return docs

    def search(
        self,
        query_vector: list[float],
        top_k: int = 20,
        source: str | None = None,
        target_vector: str = CONTENT_VECTOR,
    ) -> list[dict]:
        """Recherche dense pure (conservée pour compatibilité / tests)."""
        collection = self._client.collections.get(COLLECTION_NAME)
        filters = Filter.by_property("source").equal(source) if source else None

        result = collection.query.near_vector(
            near_vector=query_vector,
            limit=top_k,
            return_metadata=MetadataQuery(distance=True),
            filters=filters,
            target_vector=target_vector,
        )

        docs = []
        for obj in result.objects:
            docs.append({
                **obj.properties,
                "_distance": obj.metadata.distance,
                "_id": str(obj.uuid),
            })
        return docs

    def list_sources(self) -> list[str]:
        """Retourne la liste des sources uniques indexées."""
        self._ensure_connected()
        collection = self._client.collections.get(COLLECTION_NAME)
        # On récupère uniquement la propriété source pour économiser de la mémoire
        result = collection.query.fetch_objects(
            limit=10_000,
            return_properties=["source"],
        )
        sources = sorted(
            set(
                obj.properties.get("source", "")
                for obj in result.objects
                if obj.properties.get("source")
            )
        )
        return sources

    def count(self, source: str | None = None) -> int:
        """Retourne le nombre total de chunks (ou filtré par source)."""
        self._ensure_connected()
        collection = self._client.collections.get(COLLECTION_NAME)
        if source:
            resp = collection.aggregate.over_all(
                total_count=True,
                filters=Filter.by_property("source").equal(source),
            )
        else:
            resp = collection.aggregate.over_all(total_count=True)
        return resp.total_count or 0

    def get_chunk_by_index(self, source: str, chunk_index: int) -> dict | None:
        """Récupère un chunk spécifique par source + chunk_index.

        Utilisé par l'agent pour l'expansion des chunks voisins (prev/next).
        """
        self._ensure_connected()
        collection = self._client.collections.get(COLLECTION_NAME)
        result = collection.query.fetch_objects(
            limit=1,
            filters=(
                Filter.by_property("source").equal(source)
                & Filter.by_property("chunk_index").equal(chunk_index)
            ),
        )
        if result.objects:
            obj = result.objects[0]
            return {**obj.properties, "_id": str(obj.uuid)}
        return None