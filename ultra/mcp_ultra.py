"""
MCP Ultra Avancé — Architecture startup : multi-agents, mémoire longue durée,
RAG (Retrieval-Augmented Generation), queue de tâches, orchestration Claude
"""

import os
import json
import uuid
import time
import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
import anthropic
from mcp.server.fastmcp import FastMCP

load_dotenv()

mcp = FastMCP("MCP Ultra IA")
DB_PATH = Path(__file__).parent / "ultra.db"


# ─────────────────────────────────────────────
# Initialisation base de données
# ─────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        -- Mémoire longue durée
        CREATE TABLE IF NOT EXISTS memory (
            id         TEXT PRIMARY KEY,
            agent_id   TEXT,
            category   TEXT,
            content    TEXT,
            embedding  TEXT,
            importance REAL DEFAULT 0.5,
            access_count INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        );
        -- Base de connaissances (RAG)
        CREATE TABLE IF NOT EXISTS knowledge (
            id         TEXT PRIMARY KEY,
            source     TEXT,
            chunk_id   INTEGER,
            content    TEXT,
            summary    TEXT,
            keywords   TEXT,
            created_at TEXT
        );
        -- Queue de tâches
        CREATE TABLE IF NOT EXISTS tasks (
            id         TEXT PRIMARY KEY,
            agent_id   TEXT,
            type       TEXT,
            payload    TEXT,
            status     TEXT DEFAULT 'pending',
            result     TEXT,
            priority   INTEGER DEFAULT 5,
            created_at TEXT,
            updated_at TEXT
        );
        -- Agents actifs
        CREATE TABLE IF NOT EXISTS agents (
            id          TEXT PRIMARY KEY,
            name        TEXT,
            role        TEXT,
            model       TEXT,
            system_prompt TEXT,
            status      TEXT DEFAULT 'idle',
            tasks_done  INTEGER DEFAULT 0,
            created_at  TEXT
        );
        -- Historique des conversations
        CREATE TABLE IF NOT EXISTS conversations (
            id         TEXT PRIMARY KEY,
            agent_id   TEXT,
            messages   TEXT,
            summary    TEXT,
            created_at TEXT,
            updated_at TEXT
        );
    """)
    conn.commit()
    conn.close()


init_db()


def get_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY manquante dans .env")
    return anthropic.Anthropic(api_key=api_key)


def _now() -> str:
    return datetime.utcnow().isoformat()


# ─────────────────────────────────────────────
# Helpers internes
# ─────────────────────────────────────────────

def _simple_embed(text: str) -> str:
    """Pseudo-embedding basé sur des mots-clés (sans dépendance externe)."""
    words = set(text.lower().split())
    return json.dumps(sorted(list(words))[:50])


def _similarity(emb1: str, emb2: str) -> float:
    """Jaccard similarity entre deux ensembles de mots."""
    try:
        s1 = set(json.loads(emb1))
        s2 = set(json.loads(emb2))
        if not s1 or not s2:
            return 0.0
        return len(s1 & s2) / len(s1 | s2)
    except Exception:
        return 0.0


# ─────────────────────────────────────────────
# Outils MCP — Agents
# ─────────────────────────────────────────────

@mcp.tool()
def create_agent(
    name: str,
    role: str,
    system_prompt: str,
    model: str = "claude-opus-4-6",
) -> str:
    """
    Crée et enregistre un agent IA spécialisé.

    Args:
        name: Nom unique de l'agent (ex: "analyste-finance", "rédacteur-blog").
        role: Rôle/description de l'agent.
        system_prompt: Instructions système de l'agent.
        model: Modèle Claude à utiliser.
    """
    agent_id = str(uuid.uuid4())[:8]
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO agents (id,name,role,model,system_prompt,created_at) VALUES (?,?,?,?,?,?)",
        (agent_id, name, role, model, system_prompt, _now()),
    )
    conn.commit()
    conn.close()
    return json.dumps({
        "agent_id": agent_id,
        "name": name,
        "role": role,
        "model": model,
        "status": "ready",
    })


@mcp.tool()
def list_agents() -> str:
    """Liste tous les agents enregistrés avec leur statut."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id,name,role,model,status,tasks_done,created_at FROM agents ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    agents = [
        {"id": r[0], "name": r[1], "role": r[2], "model": r[3],
         "status": r[4], "tasks_done": r[5], "created_at": r[6]}
        for r in rows
    ]
    return json.dumps({"agents": agents, "total": len(agents)})


@mcp.tool()
def run_agent(
    agent_id: str,
    task: str,
    context: str = "",
    use_memory: bool = True,
) -> str:
    """
    Exécute une tâche via un agent spécifique avec accès à sa mémoire.

    Args:
        agent_id: ID de l'agent à utiliser.
        task: Description de la tâche ou question.
        context: Contexte additionnel optionnel.
        use_memory: Si True, injecte les souvenirs pertinents dans le prompt.
    """
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT * FROM agents WHERE id = ?", (agent_id,)
    ).fetchone()
    conn.close()

    if not row:
        return json.dumps({"error": f"Agent '{agent_id}' introuvable"})

    agent = {
        "id": row[0], "name": row[1], "role": row[2], "model": row[3],
        "system_prompt": row[4],
    }

    # Récupérer les souvenirs pertinents
    memory_context = ""
    if use_memory:
        memories = _recall_memories(agent_id, task, top_k=5)
        if memories:
            memory_context = "\n\n**Mémoire pertinente :**\n" + "\n".join(
                f"- [{m['category']}] {m['content']}" for m in memories
            )

    # Construire le prompt
    ctx_section = f"\n\n**Contexte fourni :**\n{context}" if context else ""
    full_prompt = f"{task}{ctx_section}{memory_context}"

    client = get_client()
    response = client.messages.create(
        model=agent["model"],
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=agent["system_prompt"],
        messages=[{"role": "user", "content": full_prompt}],
    )

    result = ""
    for block in response.content:
        if block.type == "text":
            result = block.text
            break

    # Sauvegarder dans la mémoire de l'agent
    _save_memory(
        agent_id=agent_id,
        category="task_result",
        content=f"Tâche: {task[:100]} | Résultat: {result[:200]}",
    )

    # Incrémenter le compteur de tâches
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE agents SET tasks_done = tasks_done + 1 WHERE id = ?", (agent_id,))
    conn.commit()
    conn.close()

    return json.dumps({
        "agent_id": agent_id,
        "agent_name": agent["name"],
        "task": task,
        "result": result,
        "memory_used": len(memories) if use_memory else 0,
        "tokens": response.usage.input_tokens + response.usage.output_tokens,
        "timestamp": _now(),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def orchestrate_agents(
    goal: str,
    agents_ids_json: str,
    strategy: str = "sequential",
) -> str:
    """
    Orchestre plusieurs agents pour atteindre un objectif commun.

    Args:
        goal: L'objectif global à atteindre.
        agents_ids_json: Liste JSON des IDs d'agents à utiliser (ex: ["a1","a2","a3"]).
        strategy: 'sequential' (résultats chaînés) | 'parallel' (tâches indépendantes).
    """
    try:
        agent_ids = json.loads(agents_ids_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "JSON invalide pour agents_ids_json"})

    conn = sqlite3.connect(DB_PATH)
    agents = []
    for aid in agent_ids:
        row = conn.execute("SELECT id,name,role FROM agents WHERE id = ?", (aid,)).fetchone()
        if row:
            agents.append({"id": row[0], "name": row[1], "role": row[2]})
    conn.close()

    if not agents:
        return json.dumps({"error": "Aucun agent valide trouvé"})

    # Phase 1 : Claude planifie les sous-tâches
    plan_prompt = f"""Tu es un orchestrateur d'agents IA. Tu dois décomposer l'objectif suivant en sous-tâches adaptées à chaque agent.

Objectif global : {goal}

Agents disponibles :
{json.dumps(agents, indent=2, ensure_ascii=False)}

Stratégie : {strategy}

Génère un plan JSON avec ce format :
{{
  "plan_title": "...",
  "subtasks": [
    {{"agent_id": "...", "task": "...", "context": "..."}}
  ]
}}

Assigne chaque sous-tâche à l'agent le plus adapté selon son rôle.
{'Chaque tâche reçoit le résultat de la précédente comme contexte.' if strategy == 'sequential' else 'Les tâches peuvent être exécutées indépendamment.'}
Retourne uniquement le JSON, sans commentaire."""

    client = get_client()
    plan_resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": plan_prompt}],
    )
    plan_text = ""
    for block in plan_resp.content:
        if block.type == "text":
            plan_text = block.text.strip()
            break

    try:
        # Nettoyer si Claude a ajouté des backticks
        if plan_text.startswith("```"):
            plan_text = "\n".join(plan_text.split("\n")[1:-1])
        plan = json.loads(plan_text)
    except json.JSONDecodeError:
        return json.dumps({"error": "Impossible de parser le plan", "raw": plan_text})

    # Phase 2 : Exécuter les sous-tâches
    results = []
    previous_result = ""

    for subtask in plan.get("subtasks", []):
        context = subtask.get("context", "")
        if strategy == "sequential" and previous_result:
            context = f"Résultat précédent :\n{previous_result}\n\n{context}"

        raw = run_agent(
            agent_id=subtask["agent_id"],
            task=subtask["task"],
            context=context,
        )
        result_data = json.loads(raw)
        results.append(result_data)
        previous_result = result_data.get("result", "")

    # Phase 3 : Synthèse finale
    synthesis_prompt = f"""Tu dois synthétiser les résultats de plusieurs agents IA pour atteindre l'objectif.

Objectif : {goal}

Résultats des agents :
{json.dumps([{'agent': r.get('agent_name'), 'result': r.get('result', '')[:500]} for r in results], indent=2, ensure_ascii=False)}

Génère une synthèse finale cohérente, structurée et actionnable."""

    synth_resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": synthesis_prompt}],
    )
    synthesis = ""
    for block in synth_resp.content:
        if block.type == "text":
            synthesis = block.text
            break

    return json.dumps({
        "goal": goal,
        "strategy": strategy,
        "plan_title": plan.get("plan_title", ""),
        "agents_used": len(results),
        "individual_results": results,
        "synthesis": synthesis,
        "timestamp": _now(),
    }, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# Outils MCP — Mémoire
# ─────────────────────────────────────────────

def _save_memory(agent_id: str, category: str, content: str, importance: float = 0.5):
    mem_id = hashlib.md5(f"{agent_id}{content}".encode()).hexdigest()[:12]
    embedding = _simple_embed(content)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT OR REPLACE INTO memory (id,agent_id,category,content,embedding,importance,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, (mem_id, agent_id, category, content, embedding, importance, _now(), _now()))
    conn.commit()
    conn.close()


def _recall_memories(agent_id: str, query: str, top_k: int = 5) -> list:
    query_emb = _simple_embed(query)
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id,category,content,embedding,importance FROM memory WHERE agent_id = ?",
        (agent_id,),
    ).fetchall()
    conn.close()

    scored = []
    for r in rows:
        score = _similarity(query_emb, r[3]) * 0.7 + r[4] * 0.3
        scored.append({"id": r[0], "category": r[1], "content": r[2], "score": score})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


@mcp.tool()
def save_memory(
    agent_id: str,
    category: str,
    content: str,
    importance: float = 0.5,
) -> str:
    """
    Sauvegarde un souvenir dans la mémoire longue durée d'un agent.

    Args:
        agent_id: ID de l'agent.
        category: Catégorie (ex: 'fact', 'preference', 'decision', 'context').
        content: Contenu du souvenir.
        importance: Score d'importance 0.0–1.0.
    """
    _save_memory(agent_id, category, content, importance)
    return json.dumps({"saved": True, "agent_id": agent_id, "category": category})


@mcp.tool()
def recall_memory(agent_id: str, query: str, top_k: int = 5) -> str:
    """
    Recherche les souvenirs les plus pertinents pour une requête.

    Args:
        agent_id: ID de l'agent.
        query: Requête pour la recherche sémantique.
        top_k: Nombre maximum de résultats.
    """
    memories = _recall_memories(agent_id, query, top_k)
    return json.dumps({
        "agent_id": agent_id,
        "query": query,
        "memories": memories,
        "total": len(memories),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def clear_agent_memory(agent_id: str) -> str:
    """Efface toute la mémoire d'un agent."""
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("DELETE FROM memory WHERE agent_id = ?", (agent_id,)).rowcount
    conn.commit()
    conn.close()
    return json.dumps({"deleted": count, "agent_id": agent_id})


# ─────────────────────────────────────────────
# Outils MCP — RAG (Knowledge Base)
# ─────────────────────────────────────────────

@mcp.tool()
def add_to_knowledge_base(source: str, content: str, chunk_size: int = 500) -> str:
    """
    Ajoute un document à la base de connaissances avec chunking automatique.

    Args:
        source: Identifiant de la source (ex: 'doc-rapport-2024', 'site-docs').
        content: Contenu textuel à indexer.
        chunk_size: Taille des chunks en caractères.
    """
    # Découper le contenu en chunks
    chunks = [content[i:i + chunk_size] for i in range(0, len(content), chunk_size)]
    client = get_client()
    conn = sqlite3.connect(DB_PATH)
    inserted = 0

    for i, chunk in enumerate(chunks):
        # Résumé rapide du chunk
        try:
            resp = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=100,
                messages=[{"role": "user", "content": f"Résume en 1 phrase (max 20 mots) :\n{chunk}"}],
            )
            summary = ""
            for block in resp.content:
                if block.type == "text":
                    summary = block.text.strip()
                    break
        except Exception:
            summary = chunk[:80] + "..."

        keywords = json.dumps(list(set(chunk.lower().split()))[:20])
        doc_id = hashlib.md5(f"{source}{i}{chunk}".encode()).hexdigest()[:12]

        conn.execute("""
            INSERT OR REPLACE INTO knowledge (id,source,chunk_id,content,summary,keywords,created_at)
            VALUES (?,?,?,?,?,?,?)
        """, (doc_id, source, i, chunk, summary, keywords, _now()))
        inserted += 1

    conn.commit()
    conn.close()
    return json.dumps({
        "source": source,
        "chunks_indexed": inserted,
        "total_chars": len(content),
    })


@mcp.tool()
def search_knowledge_base(query: str, top_k: int = 5) -> str:
    """
    Recherche dans la base de connaissances et génère une réponse augmentée (RAG).

    Args:
        query: Question ou requête.
        top_k: Nombre de chunks à récupérer.
    """
    query_emb = _simple_embed(query)
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id,source,content,summary,keywords FROM knowledge").fetchall()
    conn.close()

    scored = []
    for r in rows:
        score = _similarity(query_emb, _simple_embed(r[2]))
        scored.append({
            "id": r[0], "source": r[1],
            "content": r[2], "summary": r[3],
            "score": score,
        })

    top_chunks = sorted(scored, key=lambda x: x["score"], reverse=True)[:top_k]
    context = "\n\n---\n\n".join(
        f"[Source: {c['source']}]\n{c['content']}" for c in top_chunks
    )

    prompt = f"""Tu as accès à cette base de connaissances :

{context}

---
Question : {query}

Réponds en te basant uniquement sur le contexte fourni. Si l'information est insuffisante, dis-le clairement."""

    client = get_client()
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    answer = ""
    for block in response.content:
        if block.type == "text":
            answer = block.text
            break

    return json.dumps({
        "query": query,
        "answer": answer,
        "sources_used": [c["source"] for c in top_chunks],
        "chunks_retrieved": len(top_chunks),
    }, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# Outils MCP — Queue de tâches
# ─────────────────────────────────────────────

@mcp.tool()
def enqueue_task(
    task_type: str,
    payload_json: str,
    agent_id: str = "",
    priority: int = 5,
) -> str:
    """
    Ajoute une tâche dans la queue de traitement.

    Args:
        task_type: Type de tâche (ex: 'analysis', 'generation', 'monitoring').
        payload_json: Données JSON de la tâche.
        agent_id: ID de l'agent assigné (optionnel).
        priority: Priorité 1 (haute) à 10 (basse).
    """
    task_id = str(uuid.uuid4())[:12]
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO tasks (id,agent_id,type,payload,status,priority,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (task_id, agent_id, task_type, payload_json, "pending", priority, _now(), _now()),
    )
    conn.commit()
    conn.close()
    return json.dumps({"task_id": task_id, "type": task_type, "priority": priority, "status": "pending"})


@mcp.tool()
def process_pending_tasks(max_tasks: int = 5) -> str:
    """
    Traite les tâches en attente dans la queue (par priorité).

    Args:
        max_tasks: Nombre maximum de tâches à traiter.
    """
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id,agent_id,type,payload FROM tasks WHERE status='pending' ORDER BY priority ASC, created_at ASC LIMIT ?",
        (max_tasks,),
    ).fetchall()
    conn.close()

    if not rows:
        return json.dumps({"message": "Aucune tâche en attente", "processed": 0})

    client = get_client()
    processed = []

    for row in rows:
        task_id, agent_id, task_type, payload = row
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE tasks SET status='running', updated_at=? WHERE id=?",
            (_now(), task_id),
        )
        conn.commit()
        conn.close()

        try:
            payload_data = json.loads(payload) if payload else {}
            prompt = f"Traite cette tâche de type '{task_type}':\n{json.dumps(payload_data, indent=2)}\nFournis un résultat structuré."
            resp = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            result = ""
            for block in resp.content:
                if block.type == "text":
                    result = block.text
                    break
            status = "done"
        except Exception as e:
            result = str(e)
            status = "failed"

        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE tasks SET status=?, result=?, updated_at=? WHERE id=?",
            (status, result, _now(), task_id),
        )
        conn.commit()
        conn.close()
        processed.append({"task_id": task_id, "type": task_type, "status": status})

    return json.dumps({
        "processed": len(processed),
        "tasks": processed,
        "timestamp": _now(),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def get_task_status(task_id: str) -> str:
    """Retourne le statut et le résultat d'une tâche."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT id,type,status,result,priority,created_at,updated_at FROM tasks WHERE id=?",
        (task_id,),
    ).fetchone()
    conn.close()
    if not row:
        return json.dumps({"error": "Tâche introuvable"})
    return json.dumps({
        "task_id": row[0], "type": row[1], "status": row[2],
        "result": row[3], "priority": row[4],
        "created_at": row[5], "updated_at": row[6],
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def get_system_status() -> str:
    """Retourne un tableau de bord complet du système ultra avancé."""
    conn = sqlite3.connect(DB_PATH)
    agents_count = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    tasks_pending = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='pending'").fetchone()[0]
    tasks_done = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='done'").fetchone()[0]
    memory_items = conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
    knowledge_chunks = conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
    conn.close()

    return json.dumps({
        "system": "MCP Ultra IA",
        "version": "1.0.0",
        "timestamp": _now(),
        "stats": {
            "agents": agents_count,
            "tasks_pending": tasks_pending,
            "tasks_completed": tasks_done,
            "memory_items": memory_items,
            "knowledge_chunks": knowledge_chunks,
        },
        "status": "operational",
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
