# 🤖 Serveur MCP IA — Suite Complète

Plateforme MCP (Model Context Protocol) multi-modules propulsée par **Claude Opus 4.6**.

---

## 🗂 Architecture

```
Serveur-MPC-IA-/
├── server.py                  # MCP de base (7 outils IA généraux)
│
├── finance/
│   └── mcp_finance.py         # 💹 MCP Finance & Trading
│
├── surveillance/
│   └── mcp_surveillance.py    # 🖥 MCP Télésurveillance IA
│
├── saas/
│   ├── backend/main.py        # 🏗 API FastAPI (SaaS)
│   └── frontend/dashboard.html # Dashboard web complet
│
└── ultra/
    ├── mcp_ultra.py           # 🚀 MCP Multi-agents & RAG
    ├── mcp_business.py        # 💼 MCP Business IA
    └── docker-compose.yml     # Déploiement Docker
```

---

## 📦 Modules

### 🧠 `server.py` — MCP IA de base
| Outil | Description |
|---|---|
| `ask_claude` | Question directe à Claude (adaptive thinking) |
| `summarize_text` | Résumé configurable |
| `analyze_code` | Revue / debug / optimisation |
| `translate_text` | Traduction multi-langues |
| `generate_text` | Génération de contenu |
| `extract_structured_data` | Extraction JSON |
| `chat_with_history` | Conversation multi-tours |

---

### 💹 `finance/mcp_finance.py` — Trading & Analyse
| Outil | Description |
|---|---|
| `get_stock_price` | Cours en temps réel |
| `get_technical_indicators` | RSI, MACD, Bollinger, SMA, EMA |
| `get_trading_signal` | Signal ACHETER/VENDRE/CONSERVER |
| `analyze_portfolio` | Analyse & P&L du portefeuille |
| `get_financial_news_sentiment` | Actualités + analyse de sentiment |
| `backtest_simple_strategy` | Backtest SMA crossover / RSI |

---

### 🖥 `surveillance/mcp_surveillance.py` — Monitoring
| Outil | Description |
|---|---|
| `get_system_metrics` | CPU, RAM, disque, réseau, processus |
| `check_endpoint` | Health check HTTP avec latence |
| `analyze_logs_with_ai` | Analyse de logs par IA |
| `detect_anomalies` | Détection d'anomalies sur séries temporelles |
| `get_health_report` | Rapport de santé complet |
| `send_webhook_alert` | Alertes Slack / Discord / Teams |

---

### 🏗 `saas/` — Dashboard SaaS complet
- **Backend FastAPI** : API REST avec auth par token, stats, alertes
- **Dashboard web** : Interface moderne (dark mode) avec graphiques temps réel
- **Modules** : Assistant IA, Finance, Surveillance, Alertes

---

### 🚀 `ultra/mcp_ultra.py` — Multi-agents & RAG
| Outil | Description |
|---|---|
| `create_agent` | Crée un agent IA spécialisé |
| `run_agent` | Exécute une tâche via un agent |
| `orchestrate_agents` | Orchestre plusieurs agents (séquentiel/parallèle) |
| `save_memory` / `recall_memory` | Mémoire longue durée |
| `add_to_knowledge_base` | Indexation de documents (RAG) |
| `search_knowledge_base` | Recherche augmentée (RAG) |
| `enqueue_task` / `process_pending_tasks` | Queue de tâches |

---

### 💼 `ultra/mcp_business.py` — Business IA
| Outil | Description |
|---|---|
| `add_revenue_entry` | Enregistre une entrée de revenu |
| `analyze_revenue` | Analyse tendances + IA |
| `predict_revenue` | Prédiction revenus (3 scénarios) |
| `add_client` / `list_clients` | CRM intégré |
| `get_client_insights` | Churn risk, LTV, opportunités |
| `send_email` | Envoi d'email via SMTP |
| `generate_email_campaign` | Campagne email IA (A/B testing) |
| `create_automation` / `run_business_automations` | Règles d'automatisation |
| `get_business_dashboard` | KPIs + brief exécutif IA |

---

## 🚀 Installation

```bash
# 1. Cloner & configurer
git clone <repo-url>
cd Serveur-MPC-IA-
cp .env.example .env
# Éditez .env et ajoutez ANTHROPIC_API_KEY

# 2. Installer les dépendances du module souhaité
pip install -r finance/requirements.txt
pip install -r surveillance/requirements.txt
pip install -r saas/requirements.txt

# 3. Lancer un serveur MCP
python finance/mcp_finance.py
python surveillance/mcp_surveillance.py
python ultra/mcp_ultra.py
python ultra/mcp_business.py

# 4. Lancer le dashboard SaaS
cd saas && pip install -r requirements.txt
python backend/main.py
# → Ouvrir http://localhost:8000
```

## 🐳 Docker (tous les services)

```bash
cp .env.example .env  # ajoutez ANTHROPIC_API_KEY
cd ultra
docker-compose up -d
```

## ⚙️ Intégration Claude Code / Desktop

```bash
# Claude Code CLI
claude mcp add finance    -- python /path/to/finance/mcp_finance.py
claude mcp add surveillance -- python /path/to/surveillance/mcp_surveillance.py
claude mcp add ultra      -- python /path/to/ultra/mcp_ultra.py
claude mcp add business   -- python /path/to/ultra/mcp_business.py
```

## 📋 Variables d'environnement

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | **Requis** — Clé API Anthropic |
| `SMTP_HOST` | Serveur SMTP pour les emails |
| `SMTP_USER` | Utilisateur SMTP |
| `SMTP_PASSWORD` | Mot de passe SMTP |

## 🛠 Prérequis

- Python 3.10+
- Clé API Anthropic ([console.anthropic.com](https://console.anthropic.com))
- Docker (optionnel, pour le déploiement)
