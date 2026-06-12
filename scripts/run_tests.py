#!/usr/bin/env python3
"""Rejoue automatiquement tous les cas de test d'un CSV Adomatics contre l'API RAG.

Usage
-----
    python scripts/run_tests.py \\
        --csv "tests/tableau_sonnet.csv" \\
        --url http://localhost:8000 \\
        --output results/run_20260608.csv \\
        [--model gpt-4.1-mini] \\
        [--delay 2.0] \\
        [--timeout 120] \\
        [--token <jwt>]

Sortie
------
Même colonnes que le CSV source + colonnes de résultats :
    REPONSE_OBTENUE, INPUT_TOKEN_OBTENU, OUTPUT_TOKEN_OBTENU,
    TOTAL_TOKEN_OBTENU, TEMPS_REPONSE_OBTENU, AUDIT_FILE, ERREUR
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Package 'requests' manquant — pip install requests")


# ── Parsing du CSV Adomatics ───────────────────────────────────────────────────

def _find_header(path: Path) -> tuple[list[str], int]:
    """Retourne (colonnes, numéro de ligne) de la ligne d'en-tête ID_QUESTION."""
    with path.open(encoding="utf-8-sig") as fh:
        for lineno, raw in enumerate(fh):
            cols = [c.strip() for c in raw.rstrip("\n").split(";")]
            if cols and cols[0] == "ID_QUESTION":
                return cols, lineno
    raise ValueError("Colonne ID_QUESTION introuvable dans le CSV")


def _is_question_row(row: dict) -> bool:
    id_q = row.get("ID_QUESTION", "").strip()
    return bool(id_q) and ":" in id_q and not id_q.upper().startswith("NOTE")


def _parse_id_question(raw: str) -> tuple[str, str]:
    """'Q1:texte' → ('Q1', 'texte') / 'C1 (session ouverte):texte' → ('C1', 'texte')."""
    idx = raw.index(":")
    return raw[:idx].strip(), raw[idx + 1:].strip()


def load_test_cases(csv_path: Path) -> tuple[list[str], list[dict]]:
    """Charge le CSV et retourne (colonnes, lignes de test)."""
    header_cols, header_lineno = _find_header(csv_path)

    rows: list[dict] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        # Saute les lignes de métadonnées
        for _ in range(header_lineno + 1):
            fh.readline()
        reader = csv.DictReader(fh, fieldnames=header_cols, delimiter=";")
        for row in reader:
            if _is_question_row(row):
                rows.append(dict(row))

    return header_cols, rows


# ── Appel API ──────────────────────────────────────────────────────────────────

RESULT_COLS = [
    "REPONSE_OBTENUE",
    "INPUT_TOKEN_OBTENU",
    "OUTPUT_TOKEN_OBTENU",
    "TOTAL_TOKEN_OBTENU",
    "TEMPS_REPONSE_OBTENU",
    "AUDIT_FILE",
    "ERREUR",
]


def call_query(
    base_url: str,
    question: str,
    model: str | None,
    token: str | None,
    timeout: int,
) -> dict:
    """Appelle POST /query et retourne les champs résultat."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload: dict = {"question": question}
    if model:
        payload["model"] = model

    t0 = time.monotonic()
    try:
        resp = requests.post(
            f"{base_url.rstrip('/')}/query",
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        elapsed = round(time.monotonic() - t0, 2)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        return {
            "REPONSE_OBTENUE": "",
            "INPUT_TOKEN_OBTENU": "",
            "OUTPUT_TOKEN_OBTENU": "",
            "TOTAL_TOKEN_OBTENU": "",
            "TEMPS_REPONSE_OBTENU": timeout,
            "AUDIT_FILE": "",
            "ERREUR": f"Timeout après {timeout}s",
        }
    except Exception as exc:
        return {
            "REPONSE_OBTENUE": "",
            "INPUT_TOKEN_OBTENU": "",
            "OUTPUT_TOKEN_OBTENU": "",
            "TOTAL_TOKEN_OBTENU": "",
            "TEMPS_REPONSE_OBTENU": round(time.monotonic() - t0, 2),
            "AUDIT_FILE": "",
            "ERREUR": str(exc),
        }

    usage = data.get("usage") or {}
    llm   = usage.get("llm") or {}
    answer = data.get("answer", "")

    # L'audit écrit par le pipeline : on cherche le fichier le plus récent dans audits/
    audit_file = _latest_audit_file(data.get("question_id", ""))

    return {
        "REPONSE_OBTENUE":      answer,
        "INPUT_TOKEN_OBTENU":   llm.get("input_tokens", ""),
        "OUTPUT_TOKEN_OBTENU":  llm.get("output_tokens", ""),
        "TOTAL_TOKEN_OBTENU":   llm.get("total_tokens", ""),
        "TEMPS_REPONSE_OBTENU": elapsed,
        "AUDIT_FILE":           audit_file,
        "ERREUR":               data.get("error") or "",
    }


def _latest_audit_file(question_id: str) -> str:
    """Cherche le fichier d'audit correspondant à question_id dans audits/."""
    audit_dir = Path("audits")
    if not audit_dir.exists():
        return ""
    prefix = question_id[:8] if question_id else ""
    candidates = [
        f for f in audit_dir.glob(f"*_{prefix}*.json") if f.is_file()
    ] if prefix else list(audit_dir.glob("*.json"))
    if not candidates:
        return ""
    return str(max(candidates, key=lambda f: f.stat().st_mtime))


# ── Runner principal ───────────────────────────────────────────────────────────

def run(
    csv_path: Path,
    base_url: str,
    output_path: Path,
    model: str | None,
    delay: float,
    timeout: int,
    token: str | None,
) -> None:
    header_cols, test_cases = load_test_cases(csv_path)
    print(f"  {len(test_cases)} questions chargées depuis {csv_path.name}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out_cols = header_cols + RESULT_COLS

    # Écrit l'en-tête dès le départ pour que le fichier soit lisible mid-run
    with output_path.open("w", encoding="utf-8-sig", newline="") as out_fh:
        writer = csv.DictWriter(out_fh, fieldnames=out_cols, delimiter=";", extrasaction="ignore")
        writer.writeheader()

    total = len(test_cases)
    for i, row in enumerate(test_cases, start=1):
        qid_raw, question = _parse_id_question(row["ID_QUESTION"])
        print(f"\n[{i}/{total}] {qid_raw} — {question[:80]}...")

        result = call_query(base_url, question, model, token, timeout)

        if result["ERREUR"]:
            print(f"  [ERREUR] {result['ERREUR']}")
        else:
            preview = (result["REPONSE_OBTENUE"] or "")[:100].replace("\n", " ")
            print(f"  [OK] {result['TEMPS_REPONSE_OBTENU']}s | {result['TOTAL_TOKEN_OBTENU']} tokens")
            print(f"       {preview}...")

        # Écriture progressive
        with output_path.open("a", encoding="utf-8-sig", newline="") as out_fh:
            writer = csv.DictWriter(out_fh, fieldnames=out_cols, delimiter=";", extrasaction="ignore")
            writer.writerow({**row, **result})

        if delay > 0 and i < total:
            time.sleep(delay)

    print(f"\nRésultats écrits dans : {output_path}")


# ── CLI ────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Lanceur de tests RAG automatiques")
    p.add_argument("--csv",     required=True,                  help="Chemin du CSV de tests source")
    p.add_argument("--url",     default="http://localhost:8000", help="URL de base de l'API RAG")
    p.add_argument("--output",  default=None,                   help="Chemin du CSV de résultats (défaut : résultats/<date>_<csv>.csv)")
    p.add_argument("--model",   default=None,                   help="Modèle LLM (ex: gpt-4.1-mini)")
    p.add_argument("--delay",   type=float, default=1.0,        help="Pause entre chaque requête (secondes)")
    p.add_argument("--timeout", type=int,   default=180,        help="Timeout HTTP par requête (secondes)")
    p.add_argument("--token",   default=None,                   help="JWT Bearer token si l'API est protégée")
    return p


def main() -> None:
    args = _build_parser().parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        sys.exit(f"Fichier CSV introuvable : {csv_path}")

    if args.output:
        output_path = Path(args.output)
    else:
        date_str = datetime.now().strftime("%Y%m%d_%H%M")
        output_path = Path("resultats") / f"{date_str}_{csv_path.stem}_results.csv"

    print(f"RAG Test Runner")
    print(f"  Source  : {csv_path}")
    print(f"  API     : {args.url}")
    print(f"  Modèle  : {args.model or '(défaut serveur)'}")
    print(f"  Sortie  : {output_path}")
    print(f"  Délai   : {args.delay}s | Timeout : {args.timeout}s")

    run(
        csv_path    = csv_path,
        base_url    = args.url,
        output_path = output_path,
        model       = args.model,
        delay       = args.delay,
        timeout     = args.timeout,
        token       = args.token,
    )


if __name__ == "__main__":
    main()
