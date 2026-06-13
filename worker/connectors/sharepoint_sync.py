"""Client SharePoint / Microsoft Graph minimal pour la synchronisation delta.

Contrairement au ``SharepointFetcher`` MVP d'openingestion (full-download qui
jette ``lastModifiedDateTime``), ce client expose un **listing métadonnées**
(avec horodatage) séparé du téléchargement, ce qui permet de ne télécharger que
les items modifiés (delta sync).

Autonome : utilise ``msal`` + ``requests`` (déjà tirés par
``openingestion[sharepoint]``), sans dépendre des méthodes privées du fetcher.
Credentials lus depuis l'environnement (``SHAREPOINT_CLIENT_ID/SECRET/TENANT_ID``).
"""
from __future__ import annotations

import os
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone

import requests
from loguru import logger

_GRAPH = "https://graph.microsoft.com/v1.0"
_SCOPE = ["https://graph.microsoft.com/.default"]


@dataclass
class DriveItemMeta:
    """Métadonnées d'un fichier SharePoint (sans contenu)."""
    id: str
    name: str
    web_url: str
    mime: str
    last_modified: datetime | None


def _parse_graph_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # Graph renvoie ISO-8601 en UTC, ex. "2026-01-02T03:04:05Z"
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class SharepointGraphClient:
    """Client Graph minimal : token, résolution site/drive, listing, download."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        tenant_id: str | None = None,
    ) -> None:
        self.client_id = client_id or os.getenv("SHAREPOINT_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("SHAREPOINT_CLIENT_SECRET")
        self.tenant_id = tenant_id or os.getenv("SHAREPOINT_TENANT_ID")
        if not all([self.client_id, self.client_secret, self.tenant_id]):
            raise RuntimeError(
                "Credentials SharePoint manquants "
                "(SHAREPOINT_CLIENT_ID / SHAREPOINT_CLIENT_SECRET / SHAREPOINT_TENANT_ID)."
            )
        self._token: str | None = None

    # ── Auth ─────────────────────────────────────────────────────────────────

    def _headers(self) -> dict:
        if self._token is None:
            import msal

            app = msal.ConfidentialClientApplication(
                client_id=self.client_id,
                authority=f"https://login.microsoftonline.com/{self.tenant_id}",
                client_credential=self.client_secret,
            )
            result = app.acquire_token_silent(_SCOPE, account=None) or \
                app.acquire_token_for_client(scopes=_SCOPE)
            if "access_token" not in result:
                raise RuntimeError(
                    f"Échec acquisition token Graph : {result.get('error_description', result)}"
                )
            self._token = result["access_token"]
        return {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}

    def _get_json(self, url: str) -> dict:
        resp = requests.get(url, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()

    # ── Résolution site / drive ──────────────────────────────────────────────

    def resolve_site_id(self, site_url: str | None, site_name: str | None) -> str:
        if site_url:
            parsed = urllib.parse.urlparse(site_url)
            data = self._get_json(f"{_GRAPH}/sites/{parsed.netloc}:{parsed.path}")
            return data["id"]
        if site_name:
            data = self._get_json(f"{_GRAPH}/sites?search={urllib.parse.quote(site_name)}")
            value = data.get("value", [])
            if not value:
                raise RuntimeError(f"Site SharePoint introuvable : {site_name}")
            return value[0]["id"]
        raise ValueError("site_url ou site_name requis")

    def default_drive_id(self, site_id: str) -> str:
        data = self._get_json(f"{_GRAPH}/sites/{site_id}/drive")
        return data["id"]

    # ── Listing métadonnées (récursif, paginé) ───────────────────────────────

    def list_items(self, drive_id: str, folder_path: str | None = None) -> list[DriveItemMeta]:
        """Liste tous les fichiers (métadonnées seules, sans téléchargement)."""
        if folder_path:
            clean = urllib.parse.quote(folder_path.strip("/"))
            start = f"{_GRAPH}/drives/{drive_id}/root:/{clean}:/children"
        else:
            start = f"{_GRAPH}/drives/{drive_id}/root/children"

        items: list[DriveItemMeta] = []

        def traverse(url: str) -> None:
            data = self._get_json(url)
            for item in data.get("value", []):
                if "folder" in item:
                    traverse(f"{_GRAPH}/drives/{drive_id}/items/{item['id']}/children")
                elif "file" in item:
                    items.append(
                        DriveItemMeta(
                            id=item["id"],
                            name=item.get("name", "unnamed"),
                            web_url=item.get("webUrl", f"sharepoint://{item['id']}"),
                            mime=item.get("file", {}).get("mimeType", ""),
                            last_modified=_parse_graph_dt(item.get("lastModifiedDateTime")),
                        )
                    )
            next_link = data.get("@odata.nextLink")
            if next_link:
                traverse(next_link)

        traverse(start)
        return items

    # ── Téléchargement d'un item ──────────────────────────────────────────────

    def download_item(self, drive_id: str, item_id: str) -> bytes:
        resp = requests.get(
            f"{_GRAPH}/drives/{drive_id}/items/{item_id}/content",
            headers=self._headers(),
            timeout=120,
        )
        resp.raise_for_status()
        return resp.content


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
