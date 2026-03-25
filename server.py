"""
Serveur MCP (Model Context Protocol) avec intégration Claude IA
"""

import os
import json
from dotenv import load_dotenv
import anthropic
from mcp.server.fastmcp import FastMCP

load_dotenv()

# Initialisation du serveur MCP
mcp = FastMCP("Serveur MCP IA")

# Initialisation du client Anthropic
def get_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY manquante. Vérifiez votre fichier .env")
    return anthropic.Anthropic(api_key=api_key)


# ─────────────────────────────────────────────
# Outils MCP
# ─────────────────────────────────────────────

@mcp.tool()
def ask_claude(question: str, system_prompt: str = "") -> str:
    """
    Pose une question à Claude et retourne sa réponse.

    Args:
        question: La question ou le message à envoyer à Claude.
        system_prompt: (optionnel) Instructions système pour personnaliser le comportement de Claude.
    """
    client = get_client()

    messages = [{"role": "user", "content": question}]
    kwargs = {
        "model": "claude-opus-4-6",
        "max_tokens": 4096,
        "thinking": {"type": "adaptive"},
        "messages": messages,
    }
    if system_prompt:
        kwargs["system"] = system_prompt

    response = client.messages.create(**kwargs)

    # Récupérer le texte de la réponse (ignorer les blocs thinking)
    for block in response.content:
        if block.type == "text":
            return block.text

    return "Aucune réponse textuelle reçue."


@mcp.tool()
def summarize_text(text: str, language: str = "français", max_words: int = 150) -> str:
    """
    Résume un texte long en utilisant Claude.

    Args:
        text: Le texte à résumer.
        language: La langue du résumé (défaut : français).
        max_words: Nombre maximum de mots dans le résumé (défaut : 150).
    """
    client = get_client()

    prompt = (
        f"Résume le texte suivant en {language} en maximum {max_words} mots. "
        f"Sois concis et retiens l'essentiel.\n\nTexte :\n{text}"
    )

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "text":
            return block.text

    return "Impossible de générer un résumé."


@mcp.tool()
def analyze_code(code: str, language: str = "", task: str = "revue") -> str:
    """
    Analyse du code source avec Claude (revue, débogage, optimisation, explication).

    Args:
        code: Le code source à analyser.
        language: Le langage de programmation (ex: python, javascript, go…).
        task: Le type d'analyse — 'revue', 'debug', 'optimisation' ou 'explication'.
    """
    tasks = {
        "revue": "Fais une revue de code détaillée : qualité, bonnes pratiques, sécurité, lisibilité.",
        "debug": "Identifie les bugs potentiels, explique leur cause et propose des corrections.",
        "optimisation": "Suggère des optimisations de performance et d'efficacité avec des exemples.",
        "explication": "Explique ce que fait ce code, étape par étape, de façon pédagogique.",
    }
    instruction = tasks.get(task, tasks["revue"])
    lang_info = f" (langage : {language})" if language else ""

    prompt = f"{instruction}{lang_info}\n\n```\n{code}\n```"

    client = get_client()
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "text":
            return block.text

    return "Impossible d'analyser le code."


@mcp.tool()
def translate_text(text: str, target_language: str, source_language: str = "auto") -> str:
    """
    Traduit un texte dans la langue cible via Claude.

    Args:
        text: Le texte à traduire.
        target_language: La langue cible (ex: anglais, espagnol, japonais…).
        source_language: La langue source (défaut : détection automatique).
    """
    source_info = (
        f"depuis le {source_language}" if source_language != "auto" else "en détectant automatiquement la langue"
    )
    prompt = (
        f"Traduis le texte suivant {source_info} vers le {target_language}. "
        f"Retourne uniquement la traduction, sans commentaire.\n\nTexte :\n{text}"
    )

    client = get_client()
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "text":
            return block.text

    return "Impossible de traduire le texte."


@mcp.tool()
def generate_text(
    topic: str,
    format: str = "paragraphe",
    tone: str = "neutre",
    length: str = "moyen",
) -> str:
    """
    Génère du contenu textuel sur un sujet donné.

    Args:
        topic: Le sujet ou le thème du contenu à générer.
        format: Le format souhaité — 'paragraphe', 'liste', 'email', 'article', 'tweet'.
        tone: Le ton du texte — 'neutre', 'formel', 'décontracté', 'persuasif', 'humouristique'.
        length: La longueur approximative — 'court', 'moyen', 'long'.
    """
    lengths = {"court": "~50 mots", "moyen": "~150 mots", "long": "~400 mots"}
    length_hint = lengths.get(length, "~150 mots")

    prompt = (
        f"Génère un {format} sur le sujet suivant avec un ton {tone} et une longueur de {length_hint}.\n\n"
        f"Sujet : {topic}"
    )

    client = get_client()
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "text":
            return block.text

    return "Impossible de générer le contenu."


@mcp.tool()
def extract_structured_data(text: str, schema: str) -> str:
    """
    Extrait des données structurées (JSON) depuis un texte selon un schéma fourni.

    Args:
        text: Le texte source à analyser.
        schema: Description JSON du schéma attendu (ex: {"nom": "string", "âge": "number"}).
    """
    prompt = (
        f"Extrait les données du texte suivant et retourne un JSON valide correspondant à ce schéma :\n"
        f"{schema}\n\n"
        f"Texte :\n{text}\n\n"
        f"Retourne uniquement le JSON, sans explication ni balise markdown."
    )

    client = get_client()
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "text":
            raw = block.text.strip()
            # Valider que c'est du JSON valide
            try:
                json.loads(raw)
                return raw
            except json.JSONDecodeError:
                return raw  # Retourner quand même si Claude a ajouté du contexte

    return "{}"


@mcp.tool()
def chat_with_history(
    messages_json: str,
    new_message: str,
    system_prompt: str = "",
) -> str:
    """
    Conversation multi-tours avec Claude en conservant l'historique.

    Args:
        messages_json: Historique JSON des messages précédents
                       (format : [{"role": "user"|"assistant", "content": "..."}]).
        new_message: Le nouveau message de l'utilisateur.
        system_prompt: (optionnel) Instructions système.

    Returns:
        Réponse de Claude au format JSON :
        {"response": "...", "history": [...]}
    """
    try:
        history = json.loads(messages_json) if messages_json.strip() else []
    except json.JSONDecodeError:
        history = []

    history.append({"role": "user", "content": new_message})

    client = get_client()
    kwargs = {
        "model": "claude-opus-4-6",
        "max_tokens": 4096,
        "messages": history,
    }
    if system_prompt:
        kwargs["system"] = system_prompt

    response = client.messages.create(**kwargs)

    assistant_response = ""
    for block in response.content:
        if block.type == "text":
            assistant_response = block.text
            break

    history.append({"role": "assistant", "content": assistant_response})

    return json.dumps(
        {"response": assistant_response, "history": history},
        ensure_ascii=False,
        indent=2,
    )


# ─────────────────────────────────────────────
# Point d'entrée
# ─────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
