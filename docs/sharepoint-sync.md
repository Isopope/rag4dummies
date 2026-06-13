# Synchronisation SharePoint — configuration, politique de MAJ, réindexation différentielle

Ce document décrit le connecteur SharePoint planifié : comment le configurer, la
politique de mise à jour des documents, et le mécanisme de réindexation
différentielle (delta).

---

## 1. Configuration SharePoint

### 1.1 Prérequis Azure / Entra ID

L'accès SharePoint passe par **Microsoft Graph API** avec une **App Registration
Entra ID** en authentification *client credentials* (application, pas utilisateur).

1. Créer une App Registration dans Entra ID.
2. Ajouter une **permission d'application** `Sites.Read.All` (ou `Files.Read.All`)
   sur Microsoft Graph, puis **accorder le consentement administrateur**.
3. Générer un **client secret**.
4. Noter : `client_id`, `client_secret`, `tenant_id`.

### 1.2 Credentials (variables d'environnement)

Les credentials sont **lus côté serveur** (worker), **jamais stockés en base ni
passés en paramètre de tâche**. Ils sont définis dans l'environnement du worker :

```bash
SHAREPOINT_CLIENT_ID=...
SHAREPOINT_CLIENT_SECRET=...
SHAREPOINT_TENANT_ID=...
```

Lecture : [`worker/connectors/sharepoint_sync.py`](../worker/connectors/sharepoint_sync.py)
(`SharepointGraphClient`). Le scope Graph utilisé est
`https://graph.microsoft.com/.default` (permissions applicatives).

### 1.3 Enregistrer une source à synchroniser

Deux voies, équivalentes :

**UI** — page *Ingestion → Connecteurs → « Sources SharePoint planifiées »** :
bouton **Ajouter**, renseigner :
- **Nom** : libellé d'affichage.
- **URL du site SharePoint** : ex. `https://tenant.sharepoint.com/sites/MonSite`.
- **Dossier** (optionnel) : sous-dossier à indexer (vide = racine de la bibliothèque).
- **Entité** (optionnel) : métadonnée propriétaire.
- **Cadence (jours)** : intervalle de re-synchronisation (défaut **7**).
- **Prune** : supprimer les documents absents de la source (défaut activé).

**API** (admin) — `POST /connectors/configs` :
```json
{
  "name": "Docs RH",
  "site_url": "https://tenant.sharepoint.com/sites/RH",
  "folder_path": "Politiques",
  "entity": "rh",
  "interval_seconds": 604800,
  "prune": true
}
```
Endpoints associés ([`api/routers/connector_configs.py`](../api/routers/connector_configs.py)) :
`GET/POST/PATCH/DELETE /connectors/configs` et **`POST /connectors/configs/{id}/run`**
(« Sync now » — déclenchement immédiat hors cadence).

> La première synchronisation d'une source effectue l'**indexation complète**
> (base vide → tous les items sont « nouveaux »). Il n'y a donc pas de crawl
> manuel séparé à lancer.

---

## 2. Politique de mise à jour des documents

### 2.1 Principe

Chaque source enregistrée est **re-synchronisée périodiquement** (pull planifié)
selon sa cadence `interval_seconds`. À chaque cycle :

- les documents **nouveaux ou modifiés** sont (ré)ingérés ;
- les documents **supprimés à la source** sont retirés de l'index (si `prune`) ;
- les documents **inchangés** sont ignorés (voir §3, sans même les télécharger).

### 2.2 Déclenchement (beat)

La tâche beat **`dispatch_due_connector_syncs`** s'exécute toutes les **10 min**
([`worker/config.py`](../worker/config.py), `beat_schedule`). Elle sélectionne les
sources **dues** — `enabled` et `last_sync_at` nul **ou** intervalle écoulé
(`ConnectorConfigRepository.list_due`) — et dispatche pour chacune la tâche
`sync_sharepoint` ([`worker/tasks/connectors.py`](../worker/tasks/connectors.py)),
puis met à jour `last_sync_at`/`last_task_id`.

> Le beat Celery doit tourner (`celery -A worker.app beat`) en plus du worker.
> Le bouton **« Sync now »** force un cycle immédiat sans attendre la cadence.

### 2.3 Identité stable & remplacement

L'**identité** d'un document SharePoint est son **`webUrl`** (stable), pas un hash
de contenu. Conséquence : un fichier modifié **remplace** sa version précédente au
lieu de créer un doublon — le pipeline d'ingestion fait `delete_source(identité)`
avant de réinsérer ([`ingestor.py`](../ingestor.py)). Le `webUrl` est stocké dans
`documents.source_path` ; la clé de stockage (`object_key`) et le `content_hash`
sont distincts.

### 2.4 Pruning (suppressions)

Si `prune=true`, en fin de cycle on calcule `indexés_sous_le_scope − découverts`
(scope = `sharepoint:<site>:<dossier>`) et on supprime la différence des trois
surfaces (Weaviate, object store, DB) via `delete_tracked_document`
([`api/document_cleanup.py`](../api/document_cleanup.py)).

### 2.5 Statuts d'échec

La sync échoue franchement (tâche Celery **FAILURE**) en cas d'erreur de listing
ou si **tous** les items échouent ; les échecs **par document** sont collectés
(`errors[]`) sans bloquer le reste. Le statut est visible dans la liste des
sources (UI) et via l'état Celery de la tâche.

### 2.6 Cadence — choisir l'intervalle

Le fetcher ne fait pas de webhook : la fraîcheur dépend de la cadence. Repères :
- base peu active → **7 jours** (défaut), économe.
- besoin plus frais → réduire `interval_seconds` (ex. 1 jour), au prix de cycles
  plus fréquents.
- urgence ponctuelle → **« Sync now »**.

---

## 3. Réindexation différentielle (delta)

### 3.1 Pourquoi

Re-télécharger et ré-embedder **tout** le site à chaque cycle serait coûteux
(bande passante + coût LLM des embeddings/vision). La réindexation différentielle
ne traite que ce qui a changé.

### 3.2 Mécanisme

À chaque cycle, `sync_sharepoint_task` ([`worker/tasks/connectors.py`](../worker/tasks/connectors.py)) :

1. **Liste les métadonnées** des items via Graph (sans téléchargement) —
   `SharepointGraphClient.list_items` renvoie pour chaque fichier
   `{id, name, web_url, mime, last_modified}` où `last_modified` =
   `lastModifiedDateTime` Graph.
2. Pour chaque item, compare à l'état en base. **On (re)télécharge si** :
   - aucun document en base pour ce `web_url` (**nouveau**), **ou**
   - le document n'est pas en statut `INDEXED` (échec précédent → on retente), **ou**
   - `item.last_modified > documents.source_updated_at` (**modifié**).
   Sinon → **skip** (aucun téléchargement).
3. Les items à (re)ingérer sont téléchargés (`download_item`), puis passés au
   pipeline d'ingestion (upload object store → upsert PENDING → tâche d'ingestion).
   `source_updated_at` est mis à jour avec le `last_modified` de l'item.

### 3.3 Garde-fou `content_hash`

Si un item est marqué modifié par son timestamp mais que **le contenu est
identique** (sha256), le pipeline **n'effectue pas** de ré-embedding (skip), et le
`source_updated_at` est tout de même avancé pour ne pas re-télécharger en boucle.
Le `content_hash` est donc une seconde barrière après le timestamp.

### 3.4 Champs DB impliqués

Table `documents` ([`db/models/document.py`](../db/models/document.py)) :
- `source_path` — identité stable (`webUrl`).
- `object_key` — pointeur de stockage (clé object store, adressée par contenu).
- `content_hash` — sha256 du dernier contenu ingéré (détecteur de changement).
- `source_updated_at` — `lastModifiedDateTime` du dernier import réussi (base du delta).
- `source_scope` — scope du connecteur (pour le pruning).

Migration : [`db/migrations/versions/0008_add_connector_config_and_source_updated_at.py`](../db/migrations/versions/0008_add_connector_config_and_source_updated_at.py).

### 3.5 Résumé du flux par item

```
item Graph (web_url, last_modified)
        │
        ├─ pas en base ............................. → télécharger + ingérer (nouveau)
        ├─ statut ≠ INDEXED ........................ → télécharger + ingérer (retry)
        ├─ last_modified > source_updated_at ....... → télécharger
        │        └─ content_hash identique ......... → skip ré-embed, avancer source_updated_at
        │        └─ content_hash différent ......... → ré-ingérer (remplace via delete_source)
        └─ sinon ................................... → skip (aucun download)

fin de cycle : si prune → supprimer (indexés_du_scope − découverts)
```

> **Limite connue** : le listing Graph se fait par énumération récursive
> paginée (pas de *delta token* Graph). Le coût du **listing** (métadonnées) reste
> donc proportionnel au nombre d'items, mais le **téléchargement** et le
> **ré-embedding** sont bien limités aux seuls items modifiés.
