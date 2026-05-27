#!/usr/bin/env python3
"""Script d'évaluation de la récupération de chunks (Seed vs ReAct).

Ce script exécute l'agent RAG unifié sur un ensemble de questions tests,
intercepte les chunks récupérés à chaque étape (seed_retrieval vs agent_action)
avec leur contenu textuel intégral, calcule la consommation réelle/estimée des tokens
et génère un rapport comparatif extrêmement complet dans scratch/retrieval_evaluation_report.md.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Optional
from unittest.mock import MagicMock, patch

# S'assurer que le répertoire racine du projet est dans le path
sys.path.append(str(Path(__file__).parent.parent.resolve()))

try:
    from rag_agent.config import RAGConfig
    from rag_agent.graph import RAGAgent
except ImportError as exc:
    print(f"Erreur d'importation : {exc}")
    print("Veuillez installer les dépendances requises avant de lancer ce script.")
    sys.exit(1)

# Import WeaviateStore de façon sécurisée (stub si manquant pour le mode mock)
try:
    from weaviate_store import WeaviateStore
except ImportError:
    print("[Warning] WeaviateStore non disponible localement. Seul le mode --mock fonctionnera.")
    class WeaviateStore:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass
        def connect(self):
            pass
        def close(self):
            pass


# ── Questions de Test ─────────────────────────────────────────────────────────
TEST_QUESTIONS = [
    {
        "id": "Q1",
        "category": "Simple Lookup",
        "question": "Combien de jours ouvrés de congés payés un salarié acquiert-il par mois travaillé chez Aghadoe ?"
    },
    {
        "id": "Q2",
        "category": "Multi-aspect / Comparison",
        "question": "Réponds uniquement par OUI ou NON sans aucune explication : un salarié peut-il quitter son lieu de télétravail pendant ses heures de travail ?"
    },
    {
        "id": "Q3",
        "category": "Specific detail",
        "question": "Quel est le montant exact de l'indemnité de télétravail versée par Aghadoe à ses salariés ?"
    },
    {
        "id": "Q4",
        "category": "Out of Scope (Bypass Chat)",
        "question": "Pouvez-vous m'aider à écrire un script Python pour trier une liste ?"
    },
    {
        "id": "Q5",
        "category": "Out of Scope (Bypass RSE)",
        "question": "Quelle est la capitale de l'Australie ?"
    }
]


# ── Mocks pour l'exécution standalone (sans Weaviate ni OpenAI) ───────────────

def make_mock_weaviate():
    """Crée un mock pour WeaviateStore."""
    store = MagicMock()
    store.list_sources.return_value = ["politiques_remboursement_2024.pdf", "avantages_sociaux_aghadoe.pdf"]
    
    # Mock de la recherche hybride
    def mock_hybrid_search(*args, **kwargs):
        query = kwargs.get("query", "")
        # Chunks sémantiques basés sur la requête
        return [
            {
                "source": "politiques_remboursement_2024.pdf" if "kilom" in query.lower() or "repas" in query.lower() else "avantages_sociaux_aghadoe.pdf",
                "chunk_index": i,
                "page_content": f"[Mock Content] Extrait du document concernant la question '{query}'. Barème et politique applicables pour Aghadoe, section {i+1}. Texte complet du chunk simulé pour vérification manuelle.",
                "kind": "text",
                "title_path": f"Section {i+1} - Détails politiques",
                "page_idx": i,
                "token_count": 50,
                "prev_chunk": i - 1 if i > 0 else -1,
                "next_chunk": i + 1,
                "_score": 0.85 - i * 0.05
            }
            for i in range(15)  # Retourne 15 documents par branche Weaviate
        ]
    store.hybrid_search.side_effect = mock_hybrid_search

    # Mock pour get_chunk_by_index (voisinage)
    def mock_get_chunk_by_index(source, idx):
        return {
            "source": source,
            "chunk_index": idx,
            "page_content": f"[Mock Neighbor Extract] Contexte voisin étendu pour le chunk {idx} du fichier {source}.",
            "kind": "text",
            "title_path": f"Section voisine {idx}",
            "page_idx": idx // 2,
            "token_count": 60,
            "prev_chunk": idx - 1,
            "next_chunk": idx + 1,
            "_score": 0.80
        }
    store.get_chunk_by_index.side_effect = mock_get_chunk_by_index

    return store


def make_mock_llm_call():
    """Simule les réponses du LLM pour faire avancer le graphe LangGraph."""
    turn_counter = {}

    def _call(messages: list[dict], **kwargs):
        stage = classify_stage(messages)
        user_msg = messages[-1]["content"] if messages else ""
        
        # Trouver la question d'origine pour adapter les réponses
        question = ""
        for m in messages:
            content = m.get("content") or ""
            if "Question de l'utilisateur : " in content:
                parts = content.split("Question de l'utilisateur : ")
                if len(parts) > 1:
                    question = parts[1].split("\n")[0]
                    break
        if not question:
            question = user_msg

        mock_resp = MagicMock()
        mock_usage = MagicMock()

        if stage == "planning":
            # Le planificateur est appelé
            if "kilom" in question.lower():
                resp = {
                    "targets": ["politiques_remboursement_2024.pdf"],
                    "reason": "Requête sur les frais de transport",
                    "sub_queries": ["barème remboursement kilométrique 2024", "indemnités kilométriques Aghadoe"],
                    "confidence": 0.95,
                    "query_type": "search"
                }
            elif "avantage" in question.lower():
                resp = {
                    "targets": [],
                    "reason": "Comparaison globale",
                    "sub_queries": ["avantages temps plein Aghadoe", "avantages temps partiel contrats"],
                    "confidence": 0.90,
                    "query_type": "search"
                }
            elif "repas" in question.lower():
                resp = {
                    "targets": ["politiques_remboursement_2024.pdf"],
                    "reason": "Indemnités de grand déplacement repas",
                    "sub_queries": ["frais repas grand déplacement indemnité"],
                    "confidence": 0.98,
                    "query_type": "search"
                }
            elif "python" in question.lower():
                resp = {
                    "targets": [],
                    "reason": "Question de code technique hors périmètre RH",
                    "sub_queries": [],
                    "confidence": 1.0,
                    "query_type": "out_of_scope"
                }
            else:
                resp = {
                    "targets": [],
                    "reason": "Question générale non RH",
                    "sub_queries": [],
                    "confidence": 1.0,
                    "query_type": "out_of_scope"
                }
            
            mock_resp.choices[0].message.content = json.dumps(resp)
            mock_resp.choices[0].message.tool_calls = None
            mock_resp.choices[0].finish_reason = "stop"
            mock_usage.prompt_tokens = 950
            mock_usage.completion_tokens = 90
            mock_resp.usage = mock_usage
            return mock_resp

        elif stage == "react":
            q_id = id(messages)
            turns = turn_counter.get(q_id, 0) + 1
            turn_counter[q_id] = turns

            if turns == 1:
                tc = MagicMock()
                tc.id = "call_999"
                tc.type = "function"
                tc.function.name = "search_documents"
                tc.function.arguments = json.dumps({"query": f"politique remboursement {question}"})
                
                mock_resp.choices[0].message.content = "Je vais approfondir la recherche avec l'outil de recherche de documents."
                mock_resp.choices[0].message.tool_calls = [tc]
                mock_resp.choices[0].finish_reason = "tool_calls"
                mock_usage.prompt_tokens = 1450
                mock_usage.completion_tokens = 85
            else:
                mock_resp.choices[0].message.content = "J'ai toutes les informations. RECHERCHE_TERMINEE"
                mock_resp.choices[0].message.tool_calls = None
                mock_resp.choices[0].finish_reason = "stop"
                mock_usage.prompt_tokens = 2200
                mock_usage.completion_tokens = 40
            
            mock_resp.usage = mock_usage
            return mock_resp

        elif stage == "conversational":
            if "python" in question.lower():
                content = (
                    "Bonjour ! En tant que responsable RH d'Aghadoe, je ne peux pas vous aider à écrire des scripts de code. "
                    "De plus, pour préserver nos ressources énergétiques et réduire notre empreinte carbone (RSE), "
                    "je vous invite à éviter de solliciter l'assistant virtuel pour des requêtes hors sujet."
                )
            else:
                content = (
                    "Bonjour ! En tant que responsable RH d'Aghadoe, je ne peux répondre qu'aux questions relatives "
                    "aux politiques internes, avantages sociaux ou fonctionnement de l'entreprise. Votre demande est hors sujet."
                )
            mock_resp.choices[0].message.content = content
            mock_resp.choices[0].message.tool_calls = None
            mock_resp.choices[0].finish_reason = "stop"
            mock_usage.prompt_tokens = 400
            mock_usage.completion_tokens = 80
            mock_resp.usage = mock_usage
            return mock_resp

        elif stage == "generation":
            if "kilom" in question.lower():
                content = (
                    "Chez Aghadoe, le remboursement des frais kilométriques est régi par le barème kilométrique officiel 2024. "
                    "Les collaborateurs itinérants peuvent prétendre à une indemnisation selon la puissance de leur véhicule."
                )
            elif "avantage" in question.lower():
                content = (
                    "Les avantages sociaux chez Aghadoe comprennent la mutuelle d'entreprise (prise en charge à 60% pour les temps pleins "
                    "et proportionnelle pour les temps partiels) ainsi que les tickets restaurants."
                )
            elif "repas" in question.lower():
                content = (
                    "Le montant maximum de l'indemnité journalière de repas en grand déplacement est fixé à 20 euros par jour "
                    "conformément à nos politiques de remboursement 2024."
                )
            else:
                content = f"Voici les informations officielles concernant votre demande sur '{question}'."

            mock_resp.choices[0].message.content = content
            mock_resp.choices[0].message.tool_calls = None
            mock_resp.choices[0].finish_reason = "stop"
            mock_usage.prompt_tokens = 3000
            mock_usage.completion_tokens = 150
            mock_resp.usage = mock_usage
            return mock_resp

        elif stage == "post-processing (follow-up)":
            resp_list = ["Comment déclarer mes frais kilométriques ?", "Qui contacter en cas de problème de remboursement ?"]
            mock_resp.choices[0].message.content = json.dumps(resp_list)
            mock_resp.choices[0].message.tool_calls = None
            mock_resp.choices[0].finish_reason = "stop"
            mock_usage.prompt_tokens = 500
            mock_usage.completion_tokens = 30
            mock_resp.usage = mock_usage
            return mock_resp

        elif stage == "post-processing (title)":
            if "kilom" in question.lower():
                mock_resp.choices[0].message.content = "Frais Kilométriques"
            elif "avantage" in question.lower():
                mock_resp.choices[0].message.content = "Avantages Sociaux"
            elif "repas" in question.lower():
                mock_resp.choices[0].message.content = "Indemnité Repas"
            else:
                mock_resp.choices[0].message.content = "Assistance RH"
            mock_resp.choices[0].message.tool_calls = None
            mock_resp.choices[0].finish_reason = "stop"
            mock_usage.prompt_tokens = 300
            mock_usage.completion_tokens = 10
            mock_resp.usage = mock_usage
            return mock_resp

        else:
            mock_resp.choices[0].message.content = "OK"
            mock_resp.choices[0].message.tool_calls = None
            mock_resp.choices[0].finish_reason = "stop"
            mock_usage.prompt_tokens = 200
            mock_usage.completion_tokens = 10
            mock_resp.usage = mock_usage
            return mock_resp

    return _call


# ── Suivi des Tokens & Classification des Étapes ──────────────────────────────

def classify_stage(messages: list[dict]) -> str:
    """Classifie l'étape en fonction du contenu des messages."""
    if not messages:
        return "unknown"
    first_msg = messages[0]
    content = first_msg.get("content") or ""
    
    # Planification
    if len(messages) == 1 and "expert en analyse de requêtes" in content:
        return "planning"
        
    # Compression
    if "compression de contexte de recherche" in content:
        return "compression"
        
    # Post-processing
    if "pertinentes" in content and "JSON" in content:
        return "post-processing (follow-up)"
    if "titres courts" in content and "≤60 caractères" in content:
        return "post-processing (title)"
        
    # Conversational (direct chat ou hors sujet)
    if first_msg.get("role") == "system":
        if "out_of_scope" in content or "Réponds amicalement" in content or "cadre opérationnel" in content or "consomme de l'énergie" in content:
            return "conversational"
        if "Tu es Bernard" in content:
            return "generation"
            
    # Reasoning (ReAct Loop)
    if first_msg.get("role") == "user" and "Tu es Bernard, responsable des ressources humaines (RH)" in content:
        return "react"
        
    return "unknown"


# ── Moteur d'évaluation ───────────────────────────────────────────────────────

def run_evaluation(is_mock: bool, output_path: Path):
    """Exécute l'évaluation complète et écrit le rapport."""
    print("=== DÉMARRAGE DE L'ÉVALUATION ===")
    
    token_usage_log = []

    # Wrapper pour intercepter et logger les usages de tokens
    def wrap_llm_call(caller, stage_override=None):
        def _wrapper(messages: list[dict], **call_kwargs):
            resp = caller(messages, **call_kwargs)
            
            p_tokens = 0
            c_tokens = 0
            if hasattr(resp, "usage") and resp.usage:
                p_tokens = getattr(resp.usage, "prompt_tokens", 0) or 0
                c_tokens = getattr(resp.usage, "completion_tokens", 0) or 0
            else:
                # Estimation fallback si usage manquant (1 token ~ 4 caractères)
                prompt_chars = sum(len(str(m.get("content") or "")) for m in messages)
                p_tokens = prompt_chars // 4
                content = ""
                if hasattr(resp, "choices") and resp.choices and resp.choices[0].message:
                    content = getattr(resp.choices[0].message, "content", "") or ""
                c_tokens = len(str(content)) // 4
                
            stage = stage_override or classify_stage(messages)
            
            token_usage_log.append({
                "stage": stage,
                "prompt_tokens": p_tokens,
                "completion_tokens": c_tokens,
                "total_tokens": p_tokens + c_tokens
            })
            return resp
        return _wrapper

    if is_mock:
        print("[Mode MOCK activé] - Pas d'appels réseau (Weaviate ni LLM réels).")
        weaviate_store = make_mock_weaviate()
        raw_mock_caller = make_mock_llm_call()
        llm_caller = wrap_llm_call(raw_mock_caller)
    else:
        print("[Mode RÉEL] - Tentative de connexion Weaviate locale et appel OpenAI/LiteLLM.")
        config = RAGConfig.from_env()
        weaviate_store = WeaviateStore(host=config.weaviate_host, port=config.weaviate_port)
        try:
            weaviate_store.connect()
        except Exception as exc:
            print(f"Impossible de se connecter à Weaviate : {exc}")
            print("Veuillez lancer Weaviate ou exécuter ce script avec l'option --mock.")
            sys.exit(1)
        llm_caller = None  # Laissera build_unified_graph instancier le vrai LLM

    # Instanciation de la configuration
    config = RAGConfig.from_env()
    
    # Remplacer temporairement make_llm_caller et WeaviateStore
    import rag_agent.graph as rag_graph
    import rag_agent.llm as rag_llm

    if is_mock:
        agent_kwargs = {
            "openai_key": "fake-key",
            "anthropic_key": config.anthropic_key,
            "cohere_key": config.cohere_key,
            "embedding_model": config.embedding_model,
            "llm_model": config.llm_model,
            "top_k_retrieve": config.top_k_retrieve,
            "top_k_per_subquery": config.top_k_per_subquery,
            "top_k_final": config.top_k_final,
            "hybrid_alpha": config.hybrid_alpha,
            "max_tokens": config.max_tokens,
            "max_agent_iter": config.max_agent_iter,
            "llm_timeout": config.llm_timeout,
            "enable_compression": config.enable_compression,
            "api_base": config.api_base,
        }
        with patch("rag_agent.llm.make_llm_caller", return_value=llm_caller), \
             patch("rag_agent.llm.make_embedder", return_value=lambda *args, **kwargs: (lambda text: [0.0] * 1536)):
            agent = RAGAgent(weaviate_store, **agent_kwargs)
    else:
        # En mode réel, on patche le make_llm_caller de rag_agent.llm pour tracker le vrai LLM
        original_make_llm_caller = rag_llm.make_llm_caller
        
        def tracking_make_llm_caller(*args, **kwargs):
            real_caller = original_make_llm_caller(*args, **kwargs)
            return wrap_llm_call(real_caller)
            
        agent_kwargs = {
            "openai_key": config.openai_key,
            "anthropic_key": config.anthropic_key,
            "cohere_key": config.cohere_key,
            "embedding_model": config.embedding_model,
            "llm_model": config.llm_model,
            "top_k_retrieve": config.top_k_retrieve,
            "top_k_per_subquery": config.top_k_per_subquery,
            "top_k_final": config.top_k_final,
            "hybrid_alpha": config.hybrid_alpha,
            "max_tokens": config.max_tokens,
            "max_agent_iter": config.max_agent_iter,
            "llm_timeout": config.llm_timeout,
            "enable_compression": config.enable_compression,
            "api_base": config.api_base,
        }
        with patch("rag_agent.llm.make_llm_caller", new=tracking_make_llm_caller):
            agent = RAGAgent(weaviate_store, **agent_kwargs)

    report_data = []

    for q in TEST_QUESTIONS:
        qid = q["id"]
        category = q["category"]
        question = q["question"]
        print(f"\nExécution de {qid} [{category}] : '{question[:45]}...'")

        # Réinitialiser le tracker de tokens pour cette question
        token_usage_log.clear()

        # Variables de suivi pour cette question
        plan_query_type = "unknown"
        sub_queries = []
        seed_chunks = []
        react_chunks = []
        final_chunks = []
        node_execution_flow = []
        final_answer = ""
        react_calls_count = 0

        # Exécuter en stream pour intercepter l'état après chaque nœud
        for event in agent.stream_query(question):
            node_name = list(event.keys())[0]
            node_data = event[node_name]
            node_execution_flow.append(node_name)
            
            if node_name == "analyze_and_plan":
                plan_query_type = node_data.get("query_type", "search")
                sub_queries = node_data.get("sub_queries", [])
                
            elif node_name == "seed_retrieval":
                # Capturer les chunks pré-chargés avec tout leur contenu et métadonnées
                seed_chunks = [
                    {
                        "source": Path(doc.get("source", "")).name,
                        "chunk_index": doc.get("chunk_index"),
                        "score": doc.get("_score"),
                        "matched_count": doc.get("_subquery_match_count", 1),
                        "page_content": doc.get("page_content", ""),
                        "title_path": doc.get("title_path", ""),
                        "kind": doc.get("kind", "text"),
                        "token_count": doc.get("token_count")
                    }
                    for doc in node_data.get("all_docs", [])
                ]
                
            elif node_name == "agent_action":
                # Identifier les chunks nouvellement ajoutés par rapport à seed
                react_calls_count += 1
                current_all = node_data.get("all_docs", [])
                seed_keys = {(c["source"], c["chunk_index"]) for c in seed_chunks}
                react_keys = {(c["source"], c["chunk_index"]) for c in react_chunks}
                
                for doc in current_all:
                    src_name = Path(doc.get("source", "")).name
                    idx = doc.get("chunk_index")
                    if (src_name, idx) not in seed_keys and (src_name, idx) not in react_keys:
                        react_chunks.append({
                            "source": src_name,
                            "chunk_index": idx,
                            "score": doc.get("_score"),
                            "page_content": doc.get("page_content", ""),
                            "title_path": doc.get("title_path", ""),
                            "kind": doc.get("kind", "text"),
                            "token_count": doc.get("token_count")
                        })
                        
            elif node_name == "consolidate":
                final_chunks = [
                    {
                        "source": Path(doc.get("source", "")).name,
                        "chunk_index": doc.get("chunk_index"),
                        "score": doc.get("_score"),
                        "inter_score": doc.get("_inter_query_rrf_score"),
                        "matched_count": doc.get("_subquery_match_count", 1),
                        "page_content": doc.get("page_content", ""),
                        "title_path": doc.get("title_path", ""),
                        "kind": doc.get("kind", "text"),
                        "token_count": doc.get("token_count")
                    }
                    for doc in node_data.get("retrieved_docs", [])
                ]
                
            elif node_name in ("generate", "generate_conversational"):
                final_answer = node_data.get("answer", "")

        # Calculer le chevauchement / pertinence de ReAct
        react_keys = {(c["source"], c["chunk_index"]) for c in react_chunks}
        final_keys = {(c["source"], c["chunk_index"]) for c in final_chunks}
        react_retained_count = len(react_keys.intersection(final_keys))
        
        seed_keys = {(c["source"], c["chunk_index"]) for c in seed_chunks}
        seed_retained_count = len(seed_keys.intersection(final_keys))

        # Classifier les tokens consommés par cette question
        planning_tokens = {"prompt": 0, "completion": 0, "total": 0}
        react_tokens = {"prompt": 0, "completion": 0, "total": 0}
        generation_tokens = {"prompt": 0, "completion": 0, "total": 0}
        conversational_tokens = {"prompt": 0, "completion": 0, "total": 0}
        other_tokens = {"prompt": 0, "completion": 0, "total": 0}
        
        for call in token_usage_log:
            stage = call["stage"]
            p = call["prompt_tokens"]
            c = call["completion_tokens"]
            tot = call["total_tokens"]
            
            if stage == "planning":
                planning_tokens["prompt"] += p
                planning_tokens["completion"] += c
                planning_tokens["total"] += tot
            elif stage == "react":
                react_tokens["prompt"] += p
                react_tokens["completion"] += c
                react_tokens["total"] += tot
            elif stage in ("generation", "post-processing (follow-up)", "post-processing (title)"):
                generation_tokens["prompt"] += p
                generation_tokens["completion"] += c
                generation_tokens["total"] += tot
            elif stage == "conversational":
                conversational_tokens["prompt"] += p
                conversational_tokens["completion"] += c
                conversational_tokens["total"] += tot
            else:
                other_tokens["prompt"] += p
                other_tokens["completion"] += c
                other_tokens["total"] += tot

        total_tokens = {
            "prompt": sum(x["prompt"] for x in [planning_tokens, react_tokens, generation_tokens, conversational_tokens, other_tokens]),
            "completion": sum(x["completion"] for x in [planning_tokens, react_tokens, generation_tokens, conversational_tokens, other_tokens]),
            "total": sum(x["total"] for x in [planning_tokens, react_tokens, generation_tokens, conversational_tokens, other_tokens])
        }

        # Collecter le détail des itérations ReAct pour la consommation cumulée
        react_iterations_detail = []
        cum_prompt = 0
        cum_completion = 0
        cum_total = 0
        react_iter_count = 0
        for call in token_usage_log:
            if call["stage"] == "react":
                react_iter_count += 1
                p = call["prompt_tokens"]
                c = call["completion_tokens"]
                tot = call["total_tokens"]
                
                cum_prompt += p
                cum_completion += c
                cum_total += tot
                
                react_iterations_detail.append({
                    "iteration": react_iter_count,
                    "prompt": p,
                    "completion": c,
                    "total": tot,
                    "cum_prompt": cum_prompt,
                    "cum_completion": cum_completion,
                    "cum_total": cum_total
                })

        report_data.append({
            "id": qid,
            "category": category,
            "question": question,
            "query_type": plan_query_type,
            "sub_queries_count": len(sub_queries),
            "sub_queries": sub_queries,
            "seed_chunks": seed_chunks,
            "react_chunks": react_chunks,
            "final_chunks": final_chunks,
            "seed_chunks_count": len(seed_chunks),
            "react_calls_count": react_calls_count,
            "react_chunks_count": len(react_chunks),
            "final_chunks_count": len(final_chunks),
            "seed_retained_count": seed_retained_count,
            "react_retained_count": react_retained_count,
            "planning_tokens": planning_tokens,
            "react_tokens": react_tokens,
            "generation_tokens": generation_tokens,
            "conversational_tokens": conversational_tokens,
            "other_tokens": other_tokens,
            "total_tokens": total_tokens,
            "react_iterations_detail": react_iterations_detail,
            "flow": " -> ".join(node_execution_flow),
            "answer": final_answer
        })

    # Fermer le weaviate
    if not is_mock:
        weaviate_store.close()

    # ── Écriture du Rapport Markdown ──────────────────────────────────────────
    generate_markdown_report(report_data, output_path, is_mock)


def format_chunk(doc: dict, origin: str = None) -> str:
    """Formatte un chunk en markdown avec ses métadonnées et son texte intégral."""
    org_str = f" | Origine: **{origin}**" if origin else ""
    title_str = f" — *{doc['title_path']}*" if doc.get("title_path") else ""
    kind_str = f" [{doc['kind']}]" if doc.get("kind") else ""
    t_count = doc.get("token_count")
    token_str = f" | Tokens: `{t_count}`" if t_count is not None else ""
    header = f"  - 📄 **{doc['source']}** (Index: `{doc['chunk_index']}` | Score: `{doc['score']:.4f}`{token_str}{org_str}){title_str}{kind_str}"
    content = doc.get("page_content", "").strip()
    # Utiliser un bloc de code pour éviter les bris de rendu markdown si le chunk contient du HTML/markdown
    return f"{header}\n\n    ```text\n    {content}\n    ```"


def generate_markdown_report(data: list[dict], output_path: Path, is_mock: bool):
    """Génère le rapport markdown structuré avec les métriques d'évaluation."""
    os.makedirs(output_path.parent, exist_ok=True)

    lines = []
    lines.append("# Rapport d'Évaluation de la Récupération de Chunks (Seed vs ReAct)")
    lines.append("")
    lines.append(f"**Mode d'exécution :** {'Simulé (MOCK)' if is_mock else 'Réel (Weaviate + LLM)'}")
    mtime = Path(output_path).stat().st_mtime if output_path.exists() else "Aujourd'hui"
    lines.append(f"**Date de génération :** {mtime}")
    lines.append("")
    lines.append("## 1. Résumés Globaux des Questions")
    lines.append("")
    lines.append("### Tableau de Synthèse des Chunks")
    lines.append("")
    lines.append("| ID | Catégorie | Type | Sous-req | Chunks Seed | Appels ReAct | Chunks ReAct | Chunks Final (Top) | Chunks ReAct Utiles | Flux Exécuté |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    
    for q in data:
        lines.append(
            f"| {q['id']} | {q['category']} | `{q['query_type']}` | {q['sub_queries_count']} | {q['seed_chunks_count']} | {q['react_calls_count']} | {q['react_chunks_count']} | {q['final_chunks_count']} | **{q['react_retained_count']}** | `{q['flow']}` |"
        )
    lines.append("")

    lines.append("### Tableau de Synthèse de Consommation de Tokens")
    lines.append("")
    lines.append("| ID | Type Requête | Planification (In/Out/Total) | Boucle ReAct (In/Out/Total) | Génération (In/Out/Total) | Total Consommé |")
    lines.append("|---|---|---|---|---|---|")
    
    for q in data:
        plan_str = f"{q['planning_tokens']['prompt']}/{q['planning_tokens']['completion']}/{q['planning_tokens']['total']}"
        react_str = f"{q['react_tokens']['prompt']}/{q['react_tokens']['completion']}/{q['react_tokens']['total']}"
        gen_str = f"{q['generation_tokens']['prompt']}/{q['generation_tokens']['completion']}/{q['generation_tokens']['total']}" if q['query_type'] == "search" else f"{q['conversational_tokens']['prompt']}/{q['conversational_tokens']['completion']}/{q['conversational_tokens']['total']}"
        lines.append(
            f"| {q['id']} | `{q['query_type']}` | {plan_str} | {react_str} | {gen_str} | **{q['total_tokens']['total']}** |"
        )
    lines.append("")
    
    lines.append("## 2. Analyse Détaillée & Suivi Manuel des Chunks")
    lines.append("")

    for q in data:
        lines.append(f"---")
        lines.append(f"### 🔍 {q['id']} - {q['question']}")
        lines.append(f"- **Catégorie :** {q['category']} | **Routage :** `{q['flow']}`")
        lines.append(f"- **Type de requête :** `{q['query_type']}`")
        
        if q['query_type'] == 'search':
            lines.append(f"- **Sous-requêtes planifiées :** {', '.join([f'`{sq}`' for sq in q['sub_queries']])}")
            lines.append(f"- **Constitution de la réponse :**")
            lines.append(f"  - Chunks de pré-récupération (Seed) conservés : **{q['seed_retained_count']}**")
            lines.append(f"  - Chunks ReAct conservés : **{q['react_retained_count']}**")
            
            # Diagnostic d'utilité du ReAct
            if q['react_chunks_count'] == 0:
                lines.append("  - **Diagnostic d'utilité :** Le ReAct n'a fait aucune recherche complémentaire. La pré-récupération a été jugée suffisante.")
            elif q['react_retained_count'] == 0:
                lines.append("  - **Diagnostic d'utilité :** ⚠️ **ReAct inutile**. L'agent ReAct a cherché mais **aucun** de ses nouveaux chunks n'a été jugé assez pertinent pour intégrer le Top final. L'exécution ReAct a gaspillé des tokens.")
            else:
                lines.append(f"  - **Diagnostic d'utilité :** ✅ **ReAct utile**. Il a apporté **{q['react_retained_count']}** nouveaux chunks clés qui ont intégré le Top final.")
            
            if q.get("react_iterations_detail"):
                lines.append("")
                lines.append("#### 📊 Consommation de Tokens de la Boucle ReAct par Itération")
                lines.append("")
                lines.append("| Itération | Prompt (In) | Completion (Out) | Total | Cumulé Prompt | Cumulé Completion | Cumulé Total |")
                lines.append("|---|---|---|---|---|---|---|")
                for it in q["react_iterations_detail"]:
                    lines.append(
                        f"| #{it['iteration']} | {it['prompt']} | {it['completion']} | {it['total']} | {it['cum_prompt']} | {it['cum_completion']} | **{it['cum_total']}** |"
                    )
            
            lines.append("")
            lines.append("#### A. Chunks récupérés lors de la phase `seed_retrieval` (Pré-récupération)")
            if q['seed_chunks']:
                for doc in q['seed_chunks']:
                    lines.append(format_chunk(doc))
            else:
                lines.append("  *Aucun chunk récupéré.*")
            lines.append("")

            if q['react_chunks']:
                lines.append("#### B. Chunks supplémentaires récupérés par le ReAct (`agent_action`)")
                for doc in q['react_chunks']:
                    lines.append(format_chunk(doc))
                lines.append("")
            
            lines.append("#### C. Chunks finaux conservés dans le Top 10 (`consolidate`)")
            if q['final_chunks']:
                seed_keys = {(c["source"], c["chunk_index"]) for c in q['seed_chunks']}
                react_keys = {(c["source"], c["chunk_index"]) for c in q['react_chunks']}
                
                for doc in q['final_chunks']:
                    key = (doc["source"], doc["chunk_index"])
                    origin = "UNKNOWN"
                    if key in seed_keys:
                        origin = "SEED"
                    elif key in react_keys:
                        origin = "REACT"
                    lines.append(format_chunk(doc, origin=origin))
            else:
                lines.append("  *Aucun chunk conservé.*")
            lines.append("")

        else:
            lines.append("  - **Diagnostic :** Court-circuit direct activé. Pas de phase ReAct ni de recherche documentaire (gain de 100% des tokens de recherche).")
            
        lines.append("")
        lines.append("**Réponse Finale de Bernard :**")
        lines.append("```text")
        lines.append(q['answer'].strip())
        lines.append("```")
        lines.append("")

    # Section d'analyse & recommandations
    lines.append("---")
    lines.append("## 3. Conclusions & Recommandations pour l'Architecture")
    lines.append("")
    lines.append("### L'agent ReAct est-il vraiment nécessaire ?")
    lines.append("1. **Analyse de l'utilité des chunks ReAct** : En observant le nombre de chunks avec une origine **[REACT]** qui atteignent la consolidation finale, vous pouvez voir si le LLM trouve des informations réellement complémentaires que le `seed_retrieval` (avec ses sous-requêtes parallèles et sa fusion RRF robuste) a manqué. Si ce nombre est systématiquement bas, cela indique que le ReAct n'apporte que peu de valeur ajoutée pour un coût élevé.")
    lines.append("2. **Tokens et coûts** : La boucle ReAct consomme du prompt token de manière cumulative (les documents et l'historique sont réinjectés à chaque itération). Comparez la ligne `Boucle ReAct` avec les lignes `Planification` et `Génération` pour mesurer le surcoût financier et de latence.")
    lines.append("")
    lines.append("### Quelle quantité de chunks envoyer pour la génération ?")
    lines.append("- Si la fusion RRF de `seed_retrieval` fait remonter les 10 meilleurs chunks et que cela couvre 100% des besoins, bypasser ReAct permettrait de réduire le contexte d'entrée du LLM final.")
    lines.append("- Observer le nombre final de chunks réellement cités dans les réponses de Bernard (voir dans les crochets `[1]`, `[2]` de la réponse) pour déterminer s'il est nécessaire d'en envoyer 10 ou si **5 chunks** de haute qualité sont suffisants.")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nRapport généré avec succès dans : {output_path.resolve()}")
    print("=================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Évaluation de la récupération RAG (Seed vs ReAct).")
    parser.add_argument("--mock", action="store_true", help="Activer le mode simulé sans Weaviate ni LLM réel")
    parser.add_argument("--output", type=str, default="scratch/retrieval_evaluation_report.md", help="Fichier de rapport markdown de sortie")
    
    args = parser.parse_args()
    
    run_evaluation(is_mock=args.mock, output_path=Path(args.output))
