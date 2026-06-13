# RAG POC — Streamlit + Weaviate + OpenAI

Interface de chat RAG minimaliste pour interroger des documents PDF.

```
PDF → openingestion (DoclingChef) → RagChunks
    → text-embedding-3-small (OpenAI) → vecteurs
    → Weaviate (HNSW cosine) → recherche sémantique
    → gpt-4o-mini → réponse contextuelle
```

---

## Prérequis

| Outil | Version |
|---|---|
| Python | ≥ 3.10 |
| Docker + Docker Compose | récent |
| Clé OpenAI | avec accès aux API embeddings + chat |

---

## Installation

### 1. Démarrer Weaviate

```bash
cd rag_poc
docker compose up -d
```

Vérifier que Weaviate répond :

```bash
curl http://localhost:8080/v1/.well-known/ready
# → {"status":"200 OK"}
```

### 2. Créer et activer un environnement virtuel

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt

# Installer openingestion depuis le dossier parent (avec support docling)
pip install -e "../openingestion[docling]"
```

> **Note** : si vous ne voulez pas installer Docling (long à télécharger),
> vous pouvez utiliser le mode *simple* dans l'interface, qui utilise PyMuPDF.

### 4. Configurer les variables d'environnement

```bash
copy .env.example .env    # Windows
# cp .env.example .env    # Linux / macOS
```

Éditez `.env` et renseignez votre clé OpenAI :

```
OPENAI_API_KEY=sk-...
```

Raffinements d'ingestion optionnels sur le chemin `openingestion` :

```
USE_INGEST_VISION_REFINERY=true
USE_INGEST_CONTEXTUAL_RAG=true

# optionnel
INGEST_REFINERY_MODEL=gpt-4.1-mini
INGEST_REFINERY_TIMEOUT=60
INGEST_VISION_DETAIL=low
```

Notes :
- ces flags sont désactivés par défaut pour éviter un surcoût d'ingestion implicite ;
- `INGEST_REFINERY_MODEL` peut pointer vers un autre provider LiteLLM-compatible ;
- si vous utilisez un endpoint compatible OpenAI, `LITELLM_API_BASE` ou `OPENAI_API_BASE` est aussi pris en charge côté ingestion.

### 5. Lancer l'application

```bash
streamlit run app.py
```

Ouvrez [http://localhost:8501](http://localhost:8501).

---

## Utilisation

1. **Configurer la clé OpenAI** dans la barre latérale (ou dans `.env`)
2. **Uploader un PDF** et cliquer sur **▶ Ingérer le document**
3. Attendre la fin de l'indexation (peut prendre 1-5 min selon la taille et le parser)
4. **Poser des questions** dans le chat

La barre latérale permet de :
- Filtrer la recherche sur un document spécifique
- Supprimer un document de la base
- Choisir le parser (`docling`, `mineru`, `simple`) et la stratégie de découpage

---

## Documentation

- [Synchronisation SharePoint](docs/sharepoint-sync.md) — configuration SharePoint,
  politique de mise à jour des documents, et réindexation différentielle (delta).

---

## Structure du projet

```
rag_poc/
├── docker-compose.yml   # Weaviate container
├── requirements.txt
├── .env.example
├── app.py               # Interface Streamlit (point d'entrée)
├── weaviate_store.py    # Client Weaviate (CRUD)
├── ingestor.py          # PDF → chunks → embeddings → Weaviate
├── rag_chain.py         # Question → vecteur → retrieve → LLM → réponse
└── uploads/             # PDFs sauvegardés à l'ingestion (créé auto.)
```

---

## Parsers disponibles

| Parser | Description | Qualité | Vitesse |
|---|---|---|---|
| `docling` | IBM Docling (CPU-friendly) | ★★★ | ~4 p/s |
| `mineru` | MinerU (GPU recommandé) | ★★★ | ~2 p/s (CPU) |
| `simple` | PyMuPDF texte brut | ★★ | instant |

---

## Arrêter Weaviate

```bash
docker compose down          # arrêt (données conservées)
docker compose down -v       # arrêt + suppression des données
```
