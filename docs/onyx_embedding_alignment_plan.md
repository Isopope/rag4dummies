# Mise en oeuvre Onyx-first du pipeline embedding BRH

Ce document est la reference vivante de migration du pipeline embedding BRH. Chaque point suit le meme aller-retour: ce qui est verifie dans Onyx, l'etat BRH actuel, puis le TODO implemente cote BRH.

## 1. Separation contenu affiche / contenu indexe

### Onyx verifie

- `onyx/document_index/chunk_content_enrichment.py:9` construit le contenu texte indexe avec `title_prefix`, `doc_summary`, `content`, `chunk_context` et `metadata_suffix_keyword`.
- `onyx/document_index/chunk_content_enrichment.py:13` construit le contenu embedding avec `title_prefix`, `doc_summary`, `content`, `chunk_context` et `metadata_suffix_semantic`.
- `onyx/document_index/chunk_content_enrichment.py:17` nettoie les ajouts d'indexation avant de retourner les chunks aux utilisateurs.

### BRH actuel

- `ingestor.py` garde `page_content` propre, mais enrichit seulement l'embedding avec `title_path + page_content`.
- Il n'existe pas encore de module dedie a l'enrichissement.

### TODO BRH

- Ajouter `rag_agent/retrieval/content_enrichment.py`.
- Generer `embedding_content` sans modifier `page_content`.
- Preparer `doc_summary`, `chunk_context`, `metadata_suffix_semantic` et `metadata_suffix_keyword`, meme vides au debut.

### Tests

- Verifier que `page_content` reste strictement identique.
- Verifier que `embedding_content` contient titre, contenu, contexte et metadonnees quand ils existent.

## 2. Embedder passage/query

### Onyx verifie

- `onyx/natural_language_processing/search_nlp_models.py:956` expose `EmbeddingModel.encode(...)` avec un `text_type`.
- `onyx/indexing/embedder.py:151` appelle `encode(..., text_type=EmbedTextType.PASSAGE)` pour les chunks.
- Onyx utilise les types provider-specific pour differencier requete et passage.

### BRH actuel

- `llm/embedder.py` possede deja `EmbedTextType.PASSAGE` et `EmbedTextType.QUERY`.
- `make_embedder()` retourne une fonction simple qui embedde implicitement en passage.

### TODO BRH

- Ajouter `EmbeddingModel.embed_passages(texts)`.
- Ajouter `EmbeddingModel.embed_query(text)`.
- Garder `make_embedder()` compatible, mais le faire utiliser `embed_query()` pour le retrieval.

### Tests

- Verifier que `embed_passages()` transmet `EmbedTextType.PASSAGE`.
- Verifier que `embed_query()` transmet `EmbedTextType.QUERY`.
- Verifier que `make_embedder()` retourne toujours une fonction callable.

## 3. Title embeddings

### Onyx verifie

- `onyx/indexing/embedder.py:171` calcule les embeddings des titres.
- `onyx/indexing/embedder.py:180` cache les embeddings par titre pour eviter les recalculs.
- `onyx/indexing/embedder.py:197` initialise `title_embedding`.
- `onyx/indexing/embedder.py:220` attache `title_embedding` a chaque `IndexChunk`.

### BRH actuel

- `title_path` est seulement concatene au texte principal.
- Il n'existe pas de vecteur de titre separe.

### TODO BRH

- Generer `title_text` depuis le nom de source et `title_path`.
- Calculer un `title_vector` separe pour chaque chunk.
- Si `title_path` est vide, utiliser le nom de source pour eviter un titre absent.

### Tests

- Verifier que chaque chunk ingere possede `title_text`.
- Verifier que l'insertion Weaviate recoit `content_vector` et `title_vector`.

## 4. Schema Weaviate V2

### Onyx verifie

- `onyx/document_index/opensearch/schema.py:32` definit `title_vector`.
- `onyx/document_index/opensearch/schema.py:34` definit `content_vector`.
- `onyx/document_index/opensearch/schema.py:307` rend `title_vector` optionnel.
- `onyx/document_index/opensearch/schema.py:308` rend `content_vector` obligatoire.
- `onyx/document_index/opensearch/schema.py:318` verifie la coherence titre / title_vector.

### BRH actuel

- `weaviate_store.py` utilise `RagChunk` avec un vecteur unique non nomme.
- Le client Weaviate local expose `Configure.NamedVectors.none(...)`.

### TODO BRH

- Creer une collection cible `RagChunkV2`.
- Configurer deux named vectors: `content_vector` et `title_vector`.
- Ajouter les champs d'audit embedding: `embedding_model`, `embedding_provider`, `embedding_dim`, `embedding_version`, `embedding_created_at`.
- Garder `RagChunk` disponible pendant la transition.

### Tests

- Verifier que `_ensure_schema()` cree `RagChunkV2`.
- Verifier que `insert_chunks()` accepte des vecteurs nommes.

## 5. Retrieval content/title/keyword

### Onyx verifie

- `onyx/document_index/opensearch/search.py:76` utilise un poids titre vectoriel.
- `onyx/document_index/opensearch/search.py:77` utilise un poids contenu vectoriel.
- `onyx/document_index/opensearch/search.py:80` utilise un poids keyword.
- `onyx/document_index/opensearch/search.py:737` construit la recherche par `title_vector`.
- `onyx/document_index/opensearch/search.py:751` construit la recherche par `content_vector`.
- `onyx/document_index/vespa/vespa_document_index.py:586` recherche a la fois `embeddings` et `title_embedding`.

### BRH actuel

- `QueryTool` effectue deja une double recherche hybride et fusionne par weighted RRF.
- `WeaviateStore.hybrid_search()` ne cible pas encore un named vector.

### TODO BRH

- Ajouter `target_vector` a `WeaviateStore.hybrid_search()`.
- Fusionner dans `QueryTool`: contenu hybride poids `1.0`, keyword-biased poids `0.5`, titre poids `0.8`.
- Conserver les filtres stricts et les recherches ciblees par source.

### Tests

- Verifier que les appels retrieval passent `target_vector="content_vector"` et `target_vector="title_vector"`.
- Verifier que la fusion deduplique par `(source, chunk_index)`.

## 6. Fallback embedding industriel

### Onyx verifie

- `onyx/indexing/embedder.py:248` definit `embed_chunks_with_failure_handling`.
- Onyx tente un batch global, puis retente par document en cas d'echec.

### BRH actuel

- `_embed_texts()` echoue globalement si un batch echoue.

### TODO BRH

- Ajouter un fallback batch global puis par source/document.
- Logger les documents/chunks en erreur.
- Garder le comportement strict: une ingestion echoue si un document ne peut pas etre embedde.

### Tests

- Simuler un echec global et verifier le retry par chunk/source.

## 7. Mini-chunks

### Onyx verifie

- `onyx/indexing/models.py` definit `ChunkEmbedding.full_embedding` et `mini_chunk_embeddings`.
- `onyx/document_index/vespa/indexing_utils.py:159` stocke les mini embeddings sous des noms `mini_chunk_n`.

### BRH actuel

- Un chunk correspond a un seul vecteur.

### TODO BRH

- Ne pas implementer les mini-chunks dans cette premiere passe.
- Cible future: collection separee `RagMiniChunk`, avec remontage vers le chunk parent.

### Tests

- Aucun test actif dans cette passe; garder la decision documentee.

## 8. Versioning

### Onyx verifie

- `onyx/indexing/models.py` contient `EmbeddingModelDetail` et `IndexingSetting`, avec modele, dimension, provider et options d'indexation.

### BRH actuel

- Le modele d'embedding est configure, mais les chunks ne portent pas assez de metadonnees de version.

### TODO BRH

- Ajouter `embedding_version = brh-embedding-v2-onyx-aligned`.
- Stocker `embedding_model`, `embedding_provider`, `embedding_dim`, `embedding_created_at`.

### Tests

- Verifier que les chunks inseres portent les champs de versioning.
