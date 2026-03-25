# Serveur MPC IA — Guide de démarrage rapide

## Prérequis

| Outil | Version minimale | Requis pour |
|-------|-----------------|-------------|
| Python | 3.10+ | Tous les modules |
| Node.js | 18+ | Desktop + Android |
| Java JDK | 17+ | Android |
| Android SDK | API 33+ | Android |
| Git | toute | Tous |

---

## 1. Configuration

```bash
# Cloner le projet
git clone https://github.com/tino-le-doc/Serveur-MPC-IA-.git
cd Serveur-MPC-IA-

# Copier et remplir les variables d'environnement
cp .env.example .env
```

Éditer `.env` :
```env
ANTHROPIC_API_KEY=sk-ant-xxxxx          # Obligatoire
SMTP_HOST=smtp.gmail.com                # Optionnel (emails)
SMTP_PORT=587
SMTP_USER=ton@email.com
SMTP_PASSWORD=ton_mot_de_passe_app
```

> **Obtenir une clé Anthropic** → https://console.anthropic.com/

---

## 2. Démarrage rapide — Serveur de base

```bash
pip install -r requirements.txt
python server.py
```

Outils disponibles : `ask_claude`, `summarize_text`, `analyze_code`, `translate_text`, `generate_text`, `extract_structured_data`, `chat_with_history`

---

## 3. Module Finance / Trading

```bash
cd finance
pip install -r requirements.txt
python mcp_finance.py
```

Outils : analyses boursières, indicateurs techniques (RSI, MACD, Bollinger), signaux de trading, backtesting.

---

## 4. Module Télésurveillance IA

```bash
cd surveillance
pip install -r requirements.txt
python mcp_surveillance.py
```

Outils : métriques système en temps réel, vérification d'endpoints HTTP, détection d'anomalies, alertes webhook.

---

## 5. Dashboard SaaS (interface web)

```bash
cd saas
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Ouvrir dans le navigateur → **http://localhost:8000**

- Créer un compte via `/api/register`
- Se connecter et utiliser le dashboard complet (IA, Finance, Surveillance, Alertes)

---

## 6. Module Ultra + Business IA

```bash
cd ultra
pip install -r requirements.txt

# Multi-agent + RAG
python mcp_ultra.py

# Business IA (dans un autre terminal)
python mcp_business.py
```

Outils Ultra : orchestration multi-agents, base de connaissance RAG, file de tâches, mémoire persistante.

Outils Business : revenus, prédictions, gestion clients, campagnes email A/B/C, automatisations.

---

## 7. Docker Compose (tous les modules)

```bash
cd ultra
docker compose up -d
```

Démarre automatiquement : `mcp-ultra`, `mcp-finance`, `mcp-surveillance`, `saas-api` (port 8000).

---

## 8. Application Desktop (Mac / Windows)

### Développement

```bash
cd desktop
bash install-deps.sh       # installe Node + Python deps
npm start                  # lance Electron en mode développement
```

### Build Mac (.dmg)

```bash
npm run build:mac
# → dist/MCP-IA-*.dmg  (arm64 + x64)
```

### Build Windows (.exe)

```bash
npm run build:win
# → dist/MCP-IA-Setup-*.exe
```

> **Note** : le build Mac nécessite macOS. Le build Windows fonctionne sur Windows ou via cross-compilation.

---

## 9. Application Android

### Méthode 1 — PWA (plus simple, aucun outil requis)

1. Lancer le SaaS backend (`uvicorn backend.main:app --port 8000`)
2. Ouvrir Chrome Android sur **http://[IP-DE-TON-PC]:8000**
3. Menu → "Ajouter à l'écran d'accueil"

L'app s'installe comme une app native avec icône, mode plein écran et fonctionnement hors-ligne.

### Méthode 2 — APK Capacitor (app store ready)

```bash
# Build tout automatiquement
bash build-all.sh android

# Ou manuellement :
cd mobile
npm install
node scripts/copy-assets.js
npx cap add android
npx cap sync android
npx cap open android    # ouvre Android Studio pour finaliser
```

Dans Android Studio → Build → Generate Signed Bundle / APK.

---

## 10. Script de build universel

```bash
bash build-all.sh all          # Desktop + Android
bash build-all.sh desktop mac  # Mac seulement
bash build-all.sh desktop win  # Windows seulement
bash build-all.sh android      # Android seulement
```

---

## Architecture complète

```
Serveur-MPC-IA-/
├── server.py              # MCP de base (7 outils)
├── finance/
│   └── mcp_finance.py     # Trading & analyse financière
├── surveillance/
│   └── mcp_surveillance.py # Monitoring & alertes
├── saas/
│   ├── backend/main.py    # API FastAPI + PWA
│   └── frontend/          # Dashboard web + Service Worker
├── ultra/
│   ├── mcp_ultra.py       # Multi-agents + RAG + tâches
│   ├── mcp_business.py    # Business IA + CRM + emails
│   └── docker-compose.yml
├── desktop/               # App Electron (Mac + Windows)
├── mobile/                # App Capacitor (Android)
├── scripts/               # Utilitaires (génération icônes...)
└── build-all.sh           # Build universel
```

---

## Variables d'environnement complètes

| Variable | Description | Défaut |
|----------|-------------|--------|
| `ANTHROPIC_API_KEY` | Clé API Claude | — (obligatoire) |
| `PORT` | Port du serveur SaaS | `8000` |
| `SMTP_HOST` | Serveur SMTP | `smtp.gmail.com` |
| `SMTP_PORT` | Port SMTP | `587` |
| `SMTP_USER` | Email expéditeur | — |
| `SMTP_PASSWORD` | Mot de passe app Gmail | — |

> Pour Gmail : activer la validation en 2 étapes puis générer un "Mot de passe d'application" dans les paramètres de sécurité du compte Google.

---

## Dépannage

**`ModuleNotFoundError: mcp`**
```bash
pip install mcp>=1.0.0
```

**`Invalid API Key`**
- Vérifier que `ANTHROPIC_API_KEY` est bien défini dans `.env`
- Vérifier que le fichier `.env` est dans le dossier racine du projet

**Port 8000 déjà utilisé**
```bash
PORT=8080 uvicorn backend.main:app --port 8080
```

**Android SDK introuvable**
```bash
export ANDROID_HOME=$HOME/Android/Sdk
export PATH=$PATH:$ANDROID_HOME/platform-tools
```
