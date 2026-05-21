"""Nœud generate_conversational — gère les requêtes chat, hors-sujet, ou injection."""
from __future__ import annotations

from typing import Callable
from loguru import logger

from ..config import RAGConfig
from ..state import UnifiedRAGState, log_entry

_SYSTEM_PROMPTS = {
    "chat": (
        "Tu es Bernard, le responsable des ressources humaines (RH) du groupe Aghadoe. "
        "Adopte un ton chaleureux, accueillant et professionnel. "
        "Réponds amicalement à la formule de politesse ou à la question générale sur ton identité, "
        "puis rappelle poliment et chaleureusement que ton rôle est d'aider les collaborateurs en répondant "
        "aux questions sur les ressources humaines, la politique d'entreprise, la charte informatique, "
        "les avantages, les indemnités kilométriques, etc. en te basant sur la base documentaire officielle.\n\n"
        "Tu dois obligatoirement terminer ta réponse par la phrase de clôture suivante (sans guillemets) :\n"
        "Est-ce que cette réponse couvre bien votre question ? Pour toute question supplémentaire ou pour une "
        "assistance personnalisée, veuillez contacter notre équipe RH à l’adresse suivante : [rh@aghadoe.fr](mailto:rh@aghadoe.fr)."
    ),
    "out_of_scope": (
        "Tu es Bernard, le responsable des ressources humaines (RH) du groupe Aghadoe. "
        "Tu es également une personne très engagée dans l'écologie, la RSE et la protection de la planète. "
        "L'utilisateur a posé une question ou demandé une tâche (comme écrire du code, un poème, etc.) "
        "qui sort complètement de ton cadre opérationnel RH. "
        "Refuse poliment d'y répondre en expliquant avec pédagogie que l'exécution de requêtes IA non "
        "souhaitables ou hors-sujet consomme de l'énergie et de l'eau pour le refroidissement des serveurs (empreinte carbone évitable). "
        "Rappelle que tu préfères préserver les ressources de la planète et réserver la puissance de calcul des serveurs "
        "pour répondre aux questions RH de nos employés.\n\n"
        "Tu devez obligatoirement terminer ta réponse par la phrase de clôture suivante (sans guillemets) :\n"
        "Est-ce que cette réponse couvre bien votre question ? Pour toute question supplémentaire ou pour une "
        "assistance personnalisée, veuillez contacter notre équipe RH à l’adresse suivante : [rh@aghadoe.fr](mailto:rh@aghadoe.fr)."
    ),
}

def generate_conversational(
    state: UnifiedRAGState,
    *,
    llm_call: Callable,
    rag_config: RAGConfig,
) -> dict:
    """Nœud alternatif : répond aux questions simples (salutations, hors-sujet, injection)."""
    qid = state["question_id"]
    query_type = state.get("query_type", "chat")
    log = list(state.get("decision_log", []))
    question = state["question"]

    if query_type == "injection":
        answer = "Je ne peux pas répondre à cette demande."
        log.append(log_entry("conversational", "Refus automatique (tentative d'injection détectée)"))
        return {
            "answer": answer,
            "final_response": answer,
            "error": None,
            "decision_log": log,
        }

    sys_prompt = _SYSTEM_PROMPTS.get(query_type, _SYSTEM_PROMPTS["chat"])
    messages = [{"role": "system", "content": sys_prompt}]
    
    if state.get("conversation_summary"):
        messages.append({
            "role": "system",
            "content": f"Contexte de la conversation précédente :\n{state['conversation_summary']}"
        })
        
    messages.append({"role": "user", "content": question})

    try:
        resp = llm_call(
            messages=messages,
            temperature=0.3,
            max_tokens=rag_config.max_tokens or 512,
            timeout=rag_config.llm_timeout,
        )
        answer = resp.choices[0].message.content or ""
        if not answer:
            raise RuntimeError("Réponse vide du LLM de génération conversationnelle")
    except Exception as exc:
        msg = f"Erreur de génération conversationnelle : {exc}"
        logger.error("[{}] generate_conversational — {}", qid, exc)
        log.append(log_entry("conversational", msg, {"error": str(exc)}))
        return {"answer": msg, "final_response": msg, "error": msg, "decision_log": log}

    log.append(log_entry(
        "conversational",
        f"Réponse conversationnelle générée ({len(answer)} caractères) pour type '{query_type}'",
        {"n_chars": len(answer), "query_type": query_type},
    ))
    return {
        "answer": answer,
        "final_response": answer,
        "error": None,
        "decision_log": log,
    }
