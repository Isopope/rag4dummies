# BRH RAG

Plateforme RAG pour interroger des documents PDF/JSONL avec une API FastAPI,
un frontend React, une ingestion asynchrone Celery et un index vectoriel
Weaviate.

## Architecture

```text
PDF / JSONL
  -> DocumentStore local ou MinIO
  -> Celery worker
  -> openingestion ou PyMuPDF
  -> embeddings LiteLLM/OpenAI
  -> Weaviate RagChunk
  -> moteur agentique
  -> reranking API ou LLM
  -> réponse streaming SSE
  -> frontend React
```

Le projet contient deux surfaces historiques:

- `app.py`: interface Streamlit de POC.
- `api/main.py` + `frontend/`: application principale actuelle.

## Composants

- `api/`: API FastAPI, auth, endpoints RAG, ingestion, jobs, sessions, traces et évaluations.
- `frontend/`: application Vite/React pour le chat, l’ingestion, l’administration et l’observabilité.
- `rag_agent/`: pipeline RAG historique basé sur LangGraph.
- `agent_runtime/`: interface commune des moteurs agentiques, dont `react_runtime_v2`.
- `application/`: services applicatifs pour query, ingestion, conversations, observabilité et évaluation.
- `worker/`: tâches Celery pour ingestion PDF/JSONL et connecteurs.
- `db/`: modèles SQLAlchemy, repositories et migrations Alembic.
- `storage/`: stockage documentaire local ou MinIO, plus traces locales.
- `evaluation/`: runner JSONL pour comparer les moteurs agentiques.
- `weaviate_store.py`: wrapper Weaviate pour la collection `RagChunk`.
- `ingestor.py`: parsing, chunking, embedding et insertion Weaviate.

## Pipeline RAG

Le pipeline agentique exécute les étapes suivantes:

1. Analyse de la question et génération de sous-requêtes.
2. Boucle ReAct avec appels outils `search_documents` et `get_neighboring_chunk`.
3. Recherche hybride BM25 + dense dans Weaviate.
4. Fusion des résultats avec weighted RRF.
5. Reranking via API externe compatible Cohere/Infinity, avec fallback LLM.
6. Génération finale en français, strictement fondée sur les extraits.
7. Génération optionnelle de questions de suivi et d’un titre de conversation.

Les moteurs disponibles sont:

- `legacy_langgraph`: moteur historique autour du graphe LangGraph.
- `react_runtime_v2`: runtime Python explicite, compatible avec la même interface.

## Prérequis

- Python 3.10+
- Node.js 18+
- Docker et Docker Compose
- Une clé de fournisseur LLM/embedding compatible LiteLLM, par défaut OpenAI

## Installation backend

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

Copier puis adapter la configuration:

```bash
copy .env.example .env
```

Variables importantes:

- `OPENAI_API_KEY`: clé utilisée par défaut pour LLM et embeddings.
- `LLM_MODEL`: modèle de génération, par défaut `gpt-4.1`.
- `EMBEDDING_MODEL`: modèle d’embedding, par défaut `text-embedding-3-small`.
- `AGENT_ENGINE`: moteur par défaut, `legacy_langgraph` ou `react_runtime_v2`.
- `RERANKER_URL`: endpoint de reranking optionnel.
- `DATABASE_URL`: SQLite en dev, PostgreSQL possible en production.
- `MINIO_ENDPOINT`: active MinIO si renseigné, sinon stockage local `uploads/`.

## Services d’infrastructure

```bash
docker compose up -d
```

Le compose démarre:

- Weaviate sur `http://localhost:8080`
- MinIO sur `http://localhost:9001`
- Redis sur `localhost:6379`

## Lancer l’API

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Health check:

```bash
curl http://localhost:8000/health
```

## Lancer le worker

```bash
celery -A worker.app.celery_app worker -Q ingest,connectors,default --loglevel=info
```

Pour les tâches périodiques, lancer aussi Celery beat si nécessaire:

```bash
celery -A worker.app.celery_app beat --loglevel=info
```

## Lancer le frontend

```bash
cd frontend
npm install
npm run dev
```

Le frontend utilise `/api` comme base HTTP. En développement, Vite proxifie vers
`http://localhost:8000`.

## Endpoints principaux

- `POST /query`: requête RAG synchrone.
- `POST /query/stream`: requête RAG en streaming SSE.
- `POST /ingest/pdf`: upload et ingestion asynchrone d’un PDF.
- `POST /ingest/jsonl`: ingestion d’un JSONL pré-chunké.
- `GET /jobs/{task_id}`: suivi d’une ingestion.
- `GET /sources`: sources présentes dans Weaviate.
- `GET /documents`: documents suivis en base.
- `POST /feedback`: feedback utilisateur.
- `GET /observability/traces`: traces d’exécution.
- `POST /evals/compare`: comparaison de moteurs agentiques.

## Évaluation

Le dataset d’exemple est dans `evaluation/datasets/agent_eval_template.jsonl`.

```bash
python evaluation/run_eval_dataset.py --only-enabled
```

Le runner compare les moteurs demandés, sauvegarde les traces et écrit un fichier
`*.results.json`. Pour obtenir des scores qualité utiles, remplir
`expected_answer` et `expected_sources` dans le dataset.

## Notes de développement

- La collection Weaviate principale est `RagChunk`.
- Les documents expirés sont exclus de la recherche via `validity_date`.
- Les réponses incluent les chunks sources et, si disponible, une URL PDF
  présignée pour le grounding visuel.
- Les traces locales sont écrites dans `observability/traces`.
- Les fichiers `__pycache__` et `*.pyc` sont ignorés et ne doivent pas être
  versionnés.
