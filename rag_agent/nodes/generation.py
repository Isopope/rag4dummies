"""Nœuds generate et generate_post (follow-up + titre en parallèle).

Port de rag_pipeline.py:975-1023 + nouveaux nœuds de langgraph_implementation.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from loguru import logger

from ..config import RAGConfig
from ..llm import parse_json_llm
from ..state import UnifiedRAGState, log_entry


_SYSTEM_PROMPT = """Tu es un assistant expert, précis et bienveillant.

Ta tâche est de générer une réponse complète et structurée basée UNIQUEMENT sur les extraits fournis.

Règles strictes :
1. Utilise UNIQUEMENT les informations présentes dans les extraits fournis.
2. Si l'information demandée n'est pas dans les extraits, dis-le explicitement.
3. Préserve les chiffres, versions, termes techniques et détails exacts.
4. Rédige en français, dans un style clair et professionnel.
5. Ne conclus pas avec des remarques finales, notes, avis ou répétitions après la section Sources.
   La section Sources est toujours le dernier élément de ta réponse.

Mise en forme :
- Utilise le Markdown (titres, gras, listes) pour la lisibilité.
- Rédige en paragraphes fluides quand c'est possible.
- Conclus par une section Sources comme décrit ci-dessous.

Citations inline :
- Après chaque affirmation factuelle clé (chiffres, dates, contraintes, définitions, procédures…),
  place le numéro de l'extrait source entre crochets : [1], [2], etc.
- Le numéro correspond à l'index [Source N] indiqué dans le contexte fourni.
- N'ajoute PAS de citation après chaque phrase : seulement après les claims importants et vérifiables.
- Si plusieurs extraits appuient la même affirmation, liste-les tous : [1][2].
- N'invente pas de numéro hors de la plage des extraits fournis.

Règles pour la section Sources :
- Inclure "---\\n**Sources :**\\n" à la fin, suivi d'une liste numérotée des sources effectivement citées.
- Format de chaque entrée : `[N] nom_fichier.ext — p. X — *Titre de section*`
  - Omettre `— p. X` si la page est inconnue (0).
  - Omettre `— *Titre de section*` si le titre est absent.
- Lister UNIQUEMENT les entrées ayant une vraie extension de fichier (.pdf, .docx, .txt…).
- Lister UNIQUEMENT les sources dont le numéro [N] apparaît réellement dans ta réponse.
- Si aucun nom de fichier valide n'est présent, omettre la section Sources.
- LA SECTION SOURCES EST LA DERNIÈRE CHOSE QUE TU ÉCRIS."""


def _extract_cited_indices(answer: str) -> list[int]:
    """Retourne la liste ordonnée (sans doublons) des indices [N] présents dans la réponse."""
    seen: set[int] = set()
    result: list[int] = []
    for m in re.finditer(r"\[(\d+)\]", answer):
        n = int(m.group(1))
        if n not in seen:
            seen.add(n)
            result.append(n)
    return result


def _sanitize_citations(answer: str, n_docs: int) -> str:
    """Supprime silencieusement les marqueurs [N] hors de la plage 1..n_docs.

    Évite d'exposer des références fantômes inventées par le LLM.
    Les marqueurs valides ([1] à [n_docs]) sont conservés tels quels.
    """
    if n_docs <= 0:
        return re.sub(r"\[\d+\]", "", answer)

    def _replace(m: re.Match) -> str:
        n = int(m.group(1))
        return m.group(0) if 1 <= n <= n_docs else ""

    return re.sub(r"\[(\d+)\]", _replace, answer)


def _build_context_entry(index: int, doc: dict) -> str:
    """Formate un chunk pour le prompt de génération.

    Le header inclut la page et le titre de section pour que le LLM puisse
    les reprendre fidèlement dans la section Sources enrichie.
    """
    source_name = Path(doc.get("source", "inconnu")).name
    title_path  = (doc.get("title_path") or "").strip()
    content     = (doc.get("page_content") or "").strip()
    kind        = doc.get("kind", "text")
    expanded    = " (contexte étendu)" if doc.get("_expanded") else ""

    # page_idx est 0-indexé, mais 0 signifie « page inconnue » dans ce corpus.
    # On affiche page_idx + 1 uniquement si page_idx > 0.
    raw_page = doc.get("page_idx", 0)
    try:
        page_idx_int = int(raw_page)
        page_num = page_idx_int + 1 if page_idx_int > 0 else 0
    except (TypeError, ValueError):
        page_num = 0

    header = f"[Source {index}] {source_name}"
    if page_num > 0:
        header += f" — p. {page_num}"
    if title_path:
        header += f" — {title_path}"
    header += f" [{kind}{expanded}]"
    return f"{header}\n{content}"


def generate(state: UnifiedRAGState, *, llm_call: Callable, rag_config: RAGConfig) -> dict:
    """Nœud 5 : génère la réponse finale à partir des chunks rerankés."""
    qid      = state["question_id"]
    docs     = state.get("reranked_docs", [])
    question = state["question"]
    log      = list(state.get("decision_log", []))

    if not docs:
        answer = "Aucun extrait pertinent n'a été trouvé pour répondre à votre question."
        log.append(log_entry("generate", "Aucun document disponible"))
        return {"answer": answer, "final_response": answer, "error": None, "decision_log": log}

    context = "\n\n".join(_build_context_entry(i, doc) for i, doc in enumerate(docs, start=1))

    user_content = f"Contexte :\n{context}\n\nQuestion : {question}"
    if state.get("conversation_summary"):
        user_content = (
            f"Contexte de la conversation précédente :\n{state['conversation_summary']}\n\n"
            + user_content
        )

    try:
        resp = llm_call(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_content},
            ],
            temperature=0.1,
            max_tokens=rag_config.max_tokens,
            timeout=rag_config.llm_timeout * 2,
        )
        answer = resp.choices[0].message.content or ""
        if not answer:
            reason = resp.choices[0].finish_reason or "UNKNOWN"
            raise RuntimeError(f"Réponse vide (finish_reason: {reason})")
    except Exception as exc:
        msg = f"Erreur de génération : {exc}"
        logger.error("[{}] generate — {}", qid, exc)
        log.append(log_entry("generate", msg, {"error": str(exc)}))
        return {"answer": msg, "final_response": msg, "error": msg, "decision_log": log}

    answer = _sanitize_citations(answer, len(docs))

    cited_indices = _extract_cited_indices(answer)
    cited_docs    = [docs[i - 1] for i in cited_indices if 1 <= i <= len(docs)]

    log.append(log_entry(
        "generate",
        f"Réponse produite ({len(answer)} caractères, {len(cited_docs)}/{len(docs)} sources citées)",
        {"n_chars": len(answer), "n_sources": len(docs), "n_cited": len(cited_docs)},
    ))
    return {"answer": answer, "final_response": answer, "cited_docs": cited_docs, "error": None, "decision_log": log}


def generate_post(state: UnifiedRAGState, *, llm_call: Callable, rag_config: RAGConfig) -> dict:
    """Génère en parallèle les questions de suivi et le titre de la conversation.

    Fusionne generate_follow_up + generate_title en un seul nœud avec
    ThreadPoolExecutor(max_workers=2) — réduit la latence post-génération de ~50 %.
    """
    question = state["question"]
    answer   = state.get("answer", "")
    log      = list(state.get("decision_log", []))
    hidden   = dict(state.get("hidden_environment") or {})

    def _compute_follow_up() -> list[str]:
        if not rag_config.use_follow_up:
            return []
        try:
            resp = llm_call(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Tu es un assistant qui génère des questions de suivi pertinentes. "
                            "Réponds UNIQUEMENT avec un tableau JSON de 2-3 chaînes de caractères. "
                            'Exemple : ["Question 1 ?", "Question 2 ?"]'
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Question initiale : {question}\n\n"
                            f"Réponse fournie (extrait) : {answer[:800]}\n\n"
                            "Génère 2-3 questions de suivi pertinentes en français."
                        ),
                    },
                ],
                temperature=0.3,
                max_tokens=300,
            )
            raw    = resp.choices[0].message.content or "[]"
            parsed = parse_json_llm(raw)
            if isinstance(parsed, list):
                return [str(q) for q in parsed[:3]]
        except Exception as exc:
            logger.warning("generate_post (follow_up) — {}", exc)
        return []

    def _compute_title() -> str | None:
        if not rag_config.use_title_generation:
            return None
        try:
            resp = llm_call(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Tu génères des titres courts (≤60 caractères) pour des conversations. "
                            "Réponds UNIQUEMENT avec le titre, sans guillemets ni ponctuation finale."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Question : {question[:200]}\n"
                            f"Réponse (extrait) : {answer[:300]}\n\n"
                            "Génère un titre court en français."
                        ),
                    },
                ],
                temperature=0.3,
                max_tokens=60,
            )
            raw = (resp.choices[0].message.content or "").strip()
            return raw[:60] if raw else None
        except Exception as exc:
            logger.warning("generate_post (title) — {}", exc)
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        fut_follow = executor.submit(_compute_follow_up)
        fut_title  = executor.submit(_compute_title)

    suggestions: list[str]  = fut_follow.result()
    title: str | None       = fut_title.result()

    if not title:
        title = question[:50] + ("…" if len(question) > 50 else "")

    hidden["follow_ups"]         = suggestions
    hidden["conversation_title"] = title
    log.append(log_entry("follow_up", f"{len(suggestions)} suggestions générées"))
    log.append(log_entry("title",     f"Titre généré : {title!r}"))

    return {
        "follow_up_suggestions": suggestions,
        "conversation_title":    title,
        "hidden_environment":    hidden,
        "decision_log":          log,
    }
