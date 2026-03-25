# Serveur MCP IA

Un serveur **MCP (Model Context Protocol)** qui expose des outils d'intelligence artificielle powered by **Claude (Anthropic)**.

## Outils disponibles

| Outil | Description |
|---|---|
| `ask_claude` | Pose une question à Claude |
| `summarize_text` | Résume un texte long |
| `analyze_code` | Revue, debug, optimisation ou explication de code |
| `translate_text` | Traduit du texte dans n'importe quelle langue |
| `generate_text` | Génère du contenu (article, email, liste…) |
| `extract_structured_data` | Extrait du JSON structuré depuis un texte |
| `chat_with_history` | Conversation multi-tours avec historique |

## Installation

```bash
# 1. Cloner le dépôt
git clone <repo-url>
cd Serveur-MPC-IA-

# 2. Créer un environnement virtuel
python -m venv .venv
source .venv/bin/activate   # Windows : .venv\Scripts\activate

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Configurer la clé API
cp .env.example .env
# Éditez .env et ajoutez votre ANTHROPIC_API_KEY
```

## Utilisation

### Lancer le serveur

```bash
python server.py
```

### Intégration avec Claude Desktop

Ajoutez ceci dans votre `claude_desktop_config.json` :

```json
{
  "mcpServers": {
    "mcp-ia": {
      "command": "python",
      "args": ["/chemin/vers/server.py"],
      "env": {
        "ANTHROPIC_API_KEY": "votre_clé_api"
      }
    }
  }
}
```

### Intégration avec Claude Code (CLI)

```bash
claude mcp add mcp-ia -- python /chemin/vers/server.py
```

## Structure du projet

```
Serveur-MPC-IA-/
├── server.py          # Serveur MCP principal
├── requirements.txt   # Dépendances Python
├── .env.example       # Modèle de variables d'environnement
└── README.md
```

## Prérequis

- Python 3.10+
- Une clé API Anthropic ([console.anthropic.com](https://console.anthropic.com))
