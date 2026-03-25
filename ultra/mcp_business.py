"""
MCP Business IA — Automatisation intelligente pour entreprises
Outils : analyse revenus, prédiction, alertes business, emails, gestion clients
"""

import os
import json
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
import anthropic
import httpx
from mcp.server.fastmcp import FastMCP

load_dotenv()

mcp = FastMCP("MCP Business IA")
DB_PATH = Path(__file__).parent / "business.db"


# ─────────────────────────────────────────────
# Initialisation DB
# ─────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS clients (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            email      TEXT,
            phone      TEXT,
            company    TEXT,
            plan       TEXT DEFAULT 'free',
            mrr        REAL DEFAULT 0,
            status     TEXT DEFAULT 'active',
            notes      TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS revenue (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            date       TEXT NOT NULL,
            amount     REAL NOT NULL,
            type       TEXT,
            client_id  INTEGER,
            description TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS business_alerts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            level      TEXT,
            category   TEXT,
            title      TEXT,
            message    TEXT,
            action_taken INTEGER DEFAULT 0,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS email_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            to_email   TEXT,
            subject    TEXT,
            status     TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS automations (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT,
            trigger    TEXT,
            action     TEXT,
            payload    TEXT,
            enabled    INTEGER DEFAULT 1,
            runs       INTEGER DEFAULT 0,
            created_at TEXT
        );
    """)
    conn.commit()
    conn.close()


init_db()


def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))


def _now():
    return datetime.utcnow().isoformat()


# ─────────────────────────────────────────────
# Outils — Analyse Revenus
# ─────────────────────────────────────────────

@mcp.tool()
def add_revenue_entry(
    amount: float,
    revenue_type: str,
    description: str,
    date: str = "",
    client_id: int = 0,
) -> str:
    """
    Enregistre une entrée de revenu.

    Args:
        amount: Montant en euros/dollars.
        revenue_type: Type — 'subscription', 'one_time', 'service', 'refund'.
        description: Description de la transaction.
        date: Date ISO (défaut : aujourd'hui).
        client_id: ID client associé (optionnel).
    """
    entry_date = date or datetime.utcnow().date().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO revenue (date,amount,type,client_id,description,created_at) VALUES (?,?,?,?,?,?)",
        (entry_date, amount, revenue_type, client_id or None, description, _now()),
    )
    conn.commit()
    conn.close()
    return json.dumps({"saved": True, "amount": amount, "type": revenue_type, "date": entry_date})


@mcp.tool()
def analyze_revenue(period_days: int = 30) -> str:
    """
    Analyse complète des revenus avec IA : tendances, anomalies, recommandations.

    Args:
        period_days: Nombre de jours à analyser (défaut : 30).
    """
    since = (datetime.utcnow() - timedelta(days=period_days)).date().isoformat()
    conn = sqlite3.connect(DB_PATH)

    rows = conn.execute(
        "SELECT date,amount,type,description FROM revenue WHERE date >= ? ORDER BY date",
        (since,),
    ).fetchall()

    total = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM revenue WHERE date >= ?", (since,)
    ).fetchone()[0]

    by_type = conn.execute(
        "SELECT type, COALESCE(SUM(amount),0) FROM revenue WHERE date >= ? GROUP BY type",
        (since,),
    ).fetchall()

    by_day = conn.execute(
        "SELECT date, COALESCE(SUM(amount),0) FROM revenue WHERE date >= ? GROUP BY date ORDER BY date",
        (since,),
    ).fetchall()

    conn.close()

    stats = {
        "period_days": period_days,
        "since": since,
        "total_revenue": round(total, 2),
        "avg_daily": round(total / period_days, 2) if period_days > 0 else 0,
        "by_type": {r[0]: round(r[1], 2) for r in by_type},
        "daily_breakdown": [{"date": r[0], "amount": round(r[1], 2)} for r in by_day],
        "transactions": len(rows),
    }

    if not rows:
        return json.dumps({**stats, "analysis": "Aucune donnée de revenu pour cette période."})

    prompt = f"""Tu es un analyste financier expert en business SaaS.
Voici les données de revenus des {period_days} derniers jours :

{json.dumps(stats, indent=2, ensure_ascii=False)}

Analyse :
1. La tendance des revenus (croissance ? déclin ? stable ?)
2. Les anomalies ou pics inhabituels
3. La répartition par type de revenu
4. Le MRR estimé (Monthly Recurring Revenue) si applicable
5. Les recommandations pour augmenter les revenus
6. Un score de santé financière (0-100)

Sois précis avec des chiffres concrets."""

    client = get_client()
    resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )
    analysis = ""
    for block in resp.content:
        if block.type == "text":
            analysis = block.text
            break

    return json.dumps({**stats, "ai_analysis": analysis}, ensure_ascii=False, indent=2)


@mcp.tool()
def predict_revenue(forecast_days: int = 30) -> str:
    """
    Prédit les revenus futurs basé sur l'historique via IA.

    Args:
        forecast_days: Nombre de jours à prédire.
    """
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT date, COALESCE(SUM(amount),0) as daily_rev FROM revenue GROUP BY date ORDER BY date DESC LIMIT 90"
    ).fetchall()
    conn.close()

    if len(rows) < 7:
        return json.dumps({"error": "Données insuffisantes (minimum 7 jours requis)"})

    history = [{"date": r[0], "revenue": round(r[1], 2)} for r in reversed(rows)]
    total_hist = sum(r["revenue"] for r in history)
    avg_daily = total_hist / len(history)

    prompt = f"""Tu es un expert en prévision financière pour startups et SaaS.

Historique des revenus ({len(history)} jours) :
{json.dumps(history, indent=2)}

Moyenne quotidienne actuelle : {round(avg_daily, 2)}

Génère une prévision pour les {forecast_days} prochains jours.
Considère :
- Les tendances (croissance, saisonnalité, cycles)
- Le scénario pessimiste, réaliste et optimiste
- Les facteurs de risque

Réponds en JSON strict avec ce format :
{{
  "forecast_days": {forecast_days},
  "baseline_daily": <nombre>,
  "scenarios": {{
    "pessimiste": {{"total": <nombre>, "daily_avg": <nombre>, "growth_pct": <nombre>}},
    "realiste":   {{"total": <nombre>, "daily_avg": <nombre>, "growth_pct": <nombre>}},
    "optimiste":  {{"total": <nombre>, "daily_avg": <nombre>, "growth_pct": <nombre>}}
  }},
  "key_drivers": ["..."],
  "risks": ["..."],
  "recommendation": "..."
}}"""

    client = get_client()
    resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )
    raw = ""
    for block in resp.content:
        if block.type == "text":
            raw = block.text.strip()
            break

    try:
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:-1])
        return json.dumps({
            "history_days": len(history),
            "forecast": json.loads(raw),
            "generated_at": _now(),
        }, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        return json.dumps({"raw_prediction": raw, "generated_at": _now()})


# ─────────────────────────────────────────────
# Outils — Gestion Clients (CRM)
# ─────────────────────────────────────────────

@mcp.tool()
def add_client(
    name: str,
    email: str = "",
    company: str = "",
    plan: str = "free",
    mrr: float = 0.0,
    notes: str = "",
) -> str:
    """
    Ajoute un nouveau client au CRM.

    Args:
        name: Nom du client.
        email: Email du client.
        company: Entreprise.
        plan: Plan souscrit — 'free', 'starter', 'pro', 'enterprise'.
        mrr: Monthly Recurring Revenue de ce client.
        notes: Notes additionnelles.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        "INSERT INTO clients (name,email,company,plan,mrr,notes,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (name, email, company, plan, mrr, notes, _now(), _now()),
    )
    client_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return json.dumps({"client_id": client_id, "name": name, "plan": plan, "mrr": mrr})


@mcp.tool()
def get_client_insights(client_id: int) -> str:
    """
    Génère des insights IA sur un client (comportement, risque churn, opportunités).

    Args:
        client_id: ID du client.
    """
    conn = sqlite3.connect(DB_PATH)
    client_row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    if not client_row:
        conn.close()
        return json.dumps({"error": "Client introuvable"})

    revenues = conn.execute(
        "SELECT date,amount,type FROM revenue WHERE client_id = ? ORDER BY date DESC LIMIT 12",
        (client_id,),
    ).fetchall()
    conn.close()

    client_data = {
        "id": client_row[0], "name": client_row[1], "email": client_row[2],
        "company": client_row[4], "plan": client_row[5], "mrr": client_row[6],
        "status": client_row[7], "notes": client_row[8], "created_at": client_row[9],
    }
    revenue_history = [{"date": r[0], "amount": r[1], "type": r[2]} for r in revenues]

    prompt = f"""Analyse ce client et génère des insights business :

Client :
{json.dumps(client_data, indent=2, ensure_ascii=False)}

Historique des transactions :
{json.dumps(revenue_history, indent=2)}

Fournis :
1. Profil client (persona, valeur, engagement)
2. Score de risque churn (0-10, 10 = très risqué) avec justification
3. Lifetime Value estimée (LTV)
4. Opportunités d'upsell/cross-sell
5. Prochaines actions recommandées (avec priorités)
6. Message personnalisé à envoyer à ce client"""

    client = get_client()
    resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )
    insights = ""
    for block in resp.content:
        if block.type == "text":
            insights = block.text
            break

    return json.dumps({
        "client": client_data,
        "revenue_history": revenue_history,
        "ai_insights": insights,
        "generated_at": _now(),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def list_clients(status: str = "active", plan: str = "") -> str:
    """
    Liste les clients avec filtres optionnels.

    Args:
        status: Filtre — 'active', 'churned', 'trial' (vide = tous).
        plan: Filtre par plan — 'free', 'starter', 'pro', 'enterprise' (vide = tous).
    """
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT id,name,email,company,plan,mrr,status,created_at FROM clients WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if plan:
        query += " AND plan = ?"
        params.append(plan)
    query += " ORDER BY mrr DESC"
    rows = conn.execute(query, params).fetchall()

    total_mrr = conn.execute(
        "SELECT COALESCE(SUM(mrr),0) FROM clients WHERE status='active'"
    ).fetchone()[0]
    conn.close()

    clients = [
        {"id": r[0], "name": r[1], "email": r[2], "company": r[3],
         "plan": r[4], "mrr": r[5], "status": r[6], "created_at": r[7]}
        for r in rows
    ]
    return json.dumps({
        "clients": clients,
        "total": len(clients),
        "total_mrr": round(total_mrr, 2),
    }, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# Outils — Email & Automatisation
# ─────────────────────────────────────────────

@mcp.tool()
def send_email(
    to_email: str,
    subject: str,
    body: str,
    smtp_host: str = "",
    smtp_port: int = 587,
    smtp_user: str = "",
    smtp_password: str = "",
) -> str:
    """
    Envoie un email via SMTP (ou simule si credentials non fournis).

    Args:
        to_email: Destinataire.
        subject: Objet de l'email.
        body: Corps du message (HTML ou texte).
        smtp_host: Serveur SMTP (ex: smtp.gmail.com). Utilise SMTP_HOST de .env si vide.
        smtp_port: Port SMTP (défaut : 587).
        smtp_user: Utilisateur SMTP. Utilise SMTP_USER de .env si vide.
        smtp_password: Mot de passe SMTP. Utilise SMTP_PASSWORD de .env si vide.
    """
    host = smtp_host or os.getenv("SMTP_HOST", "")
    user = smtp_user or os.getenv("SMTP_USER", "")
    password = smtp_password or os.getenv("SMTP_PASSWORD", "")

    status = "simulated"
    error = ""

    if host and user and password:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = user
            msg["To"] = to_email
            msg.attach(MIMEText(body, "html" if "<" in body else "plain"))
            with smtplib.SMTP(host, smtp_port) as server:
                server.starttls()
                server.login(user, password)
                server.sendmail(user, to_email, msg.as_string())
            status = "sent"
        except Exception as e:
            status = "failed"
            error = str(e)
    else:
        status = "simulated"

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO email_log (to_email,subject,status,created_at) VALUES (?,?,?,?)",
        (to_email, subject, status, _now()),
    )
    conn.commit()
    conn.close()

    return json.dumps({
        "to": to_email, "subject": subject,
        "status": status, "error": error,
        "note": "Configurez SMTP_HOST/SMTP_USER/SMTP_PASSWORD dans .env pour envoyer de vrais emails.",
    })


@mcp.tool()
def generate_email_campaign(
    campaign_type: str,
    target_segment: str,
    product_name: str,
    key_message: str,
) -> str:
    """
    Génère une campagne email complète avec IA (objet, corps, CTA).

    Args:
        campaign_type: Type — 'onboarding', 'upsell', 'churn_prevention', 'newsletter', 'promo'.
        target_segment: Segment cible (ex: 'clients pro inactifs', 'nouveaux inscrits').
        product_name: Nom du produit ou service.
        key_message: Message principal à transmettre.
    """
    prompt = f"""Tu es un expert en email marketing B2B/SaaS.
Génère une campagne email de type '{campaign_type}' pour :
- Segment : {target_segment}
- Produit : {product_name}
- Message clé : {key_message}

Crée 3 variantes d'email (A/B/C testing) avec pour chacun :
1. Objet accrocheur (max 60 caractères)
2. Préheader (max 100 caractères)
3. Corps de l'email en HTML propre et responsive
4. Call-to-Action principal
5. P.S. (post-scriptum) percutant

Optimise pour un taux d'ouverture élevé et des conversions.
Réponds en JSON :
{{
  "campaign_type": "...",
  "variants": [
    {{
      "variant": "A",
      "subject": "...",
      "preheader": "...",
      "html_body": "...",
      "cta_text": "...",
      "cta_url": "{{CTA_URL}}",
      "ps": "..."
    }}
  ],
  "best_send_time": "...",
  "tips": ["..."]
}}"""

    client = get_client()
    resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = ""
    for block in resp.content:
        if block.type == "text":
            raw = block.text.strip()
            break

    try:
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:-1])
        return raw
    except Exception:
        return raw


@mcp.tool()
def create_automation(
    name: str,
    trigger: str,
    action: str,
    payload_json: str = "{}",
) -> str:
    """
    Crée une règle d'automatisation business.

    Args:
        name: Nom de l'automatisation (ex: 'Alerte churn client').
        trigger: Déclencheur (ex: 'client_inactive_30days', 'revenue_drop_20pct', 'new_signup').
        action: Action à effectuer (ex: 'send_email', 'create_alert', 'notify_webhook').
        payload_json: Paramètres JSON de l'action.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO automations (name,trigger,action,payload,created_at) VALUES (?,?,?,?,?)",
        (name, trigger, action, payload_json, _now()),
    )
    conn.commit()
    conn.close()
    return json.dumps({
        "created": True,
        "name": name,
        "trigger": trigger,
        "action": action,
    })


@mcp.tool()
def run_business_automations() -> str:
    """
    Évalue et exécute les automatisations business actives.
    Analyse les données business et déclenche les actions configurées.
    """
    conn = sqlite3.connect(DB_PATH)
    automations = conn.execute(
        "SELECT id,name,trigger,action,payload FROM automations WHERE enabled = 1"
    ).fetchall()

    # Données de contexte pour évaluation
    total_clients = conn.execute("SELECT COUNT(*) FROM clients WHERE status='active'").fetchone()[0]
    recent_revenue = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM revenue WHERE date >= ?",
        ((datetime.utcnow() - timedelta(days=7)).date().isoformat(),),
    ).fetchone()[0]
    prev_revenue = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM revenue WHERE date BETWEEN ? AND ?",
        (
            (datetime.utcnow() - timedelta(days=14)).date().isoformat(),
            (datetime.utcnow() - timedelta(days=7)).date().isoformat(),
        ),
    ).fetchone()[0]
    conn.close()

    context = {
        "active_clients": total_clients,
        "revenue_last_7d": round(recent_revenue, 2),
        "revenue_prev_7d": round(prev_revenue, 2),
        "revenue_change_pct": round(
            (recent_revenue - prev_revenue) / prev_revenue * 100 if prev_revenue else 0, 1
        ),
    }

    if not automations:
        return json.dumps({"message": "Aucune automatisation configurée", "context": context})

    prompt = f"""Tu es un moteur d'automatisation business intelligent.

Contexte business actuel :
{json.dumps(context, indent=2)}

Automatisations configurées :
{json.dumps([{"name": a[1], "trigger": a[2], "action": a[3]} for a in automations], indent=2)}

Pour chaque automatisation, détermine :
1. Si le trigger est activé dans le contexte actuel (true/false)
2. L'urgence (1-10)
3. Le message d'action recommandé

Réponds en JSON :
{{
  "triggered": [
    {{"name": "...", "action": "...", "message": "...", "urgency": <1-10>}}
  ],
  "not_triggered": ["..."],
  "business_summary": "..."
}}"""

    client = get_client()
    resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = ""
    for block in resp.content:
        if block.type == "text":
            raw = block.text.strip()
            break

    try:
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:-1])
        evaluation = json.loads(raw)
    except Exception:
        evaluation = {"raw": raw}

    # Créer des alertes pour les automatisations déclenchées
    triggered = evaluation.get("triggered", [])
    for t in triggered:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO business_alerts (level,category,title,message,created_at) VALUES (?,?,?,?,?)",
            (
                "WARNING" if t.get("urgency", 5) >= 7 else "INFO",
                "automation",
                t.get("name", ""),
                t.get("message", ""),
                _now(),
            ),
        )
        conn.commit()
        conn.close()

    return json.dumps({
        "context": context,
        "evaluation": evaluation,
        "automations_checked": len(automations),
        "triggered_count": len(triggered),
        "timestamp": _now(),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def get_business_dashboard() -> str:
    """
    Tableau de bord business complet avec KPIs et recommandations IA.
    """
    conn = sqlite3.connect(DB_PATH)

    today = datetime.utcnow().date().isoformat()
    month_start = datetime.utcnow().replace(day=1).date().isoformat()

    mrr = conn.execute(
        "SELECT COALESCE(SUM(mrr),0) FROM clients WHERE status='active'"
    ).fetchone()[0]
    total_clients = conn.execute("SELECT COUNT(*) FROM clients WHERE status='active'").fetchone()[0]
    revenue_mtd = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM revenue WHERE date >= ?", (month_start,)
    ).fetchone()[0]
    churn_risk = conn.execute(
        "SELECT COUNT(*) FROM clients WHERE status='active' AND plan='free'"
    ).fetchone()[0]
    top_clients = conn.execute(
        "SELECT name,plan,mrr FROM clients WHERE status='active' ORDER BY mrr DESC LIMIT 5"
    ).fetchall()
    recent_revenue = conn.execute(
        "SELECT date,SUM(amount) FROM revenue WHERE date >= ? GROUP BY date ORDER BY date DESC LIMIT 7",
        ((datetime.utcnow() - timedelta(days=7)).date().isoformat(),),
    ).fetchall()
    conn.close()

    kpis = {
        "mrr": round(mrr, 2),
        "arr": round(mrr * 12, 2),
        "active_clients": total_clients,
        "revenue_mtd": round(revenue_mtd, 2),
        "arpu": round(mrr / total_clients, 2) if total_clients > 0 else 0,
        "churn_risk_clients": churn_risk,
        "top_clients": [{"name": r[0], "plan": r[1], "mrr": r[2]} for r in top_clients],
        "daily_revenue_7d": [{"date": r[0], "amount": round(r[1], 2)} for r in recent_revenue],
    }

    prompt = f"""Tu es un conseiller business expert en SaaS/startups.
Voici les KPIs actuels :

{json.dumps(kpis, indent=2)}

Génère un brief exécutif (pour un CEO) incluant :
1. État général du business (2-3 phrases)
2. Les 3 métriques les plus préoccupantes
3. Les 3 opportunités à saisir immédiatement
4. Plan d'action prioritaire pour les 7 prochains jours
5. Projection MRR pour les 3 prochains mois (si tendance maintenue)"""

    client = get_client()
    resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1500,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )
    brief = ""
    for block in resp.content:
        if block.type == "text":
            brief = block.text
            break

    return json.dumps({
        "kpis": kpis,
        "executive_brief": brief,
        "generated_at": _now(),
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
