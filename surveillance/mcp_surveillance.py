"""
MCP Télésurveillance IA — Monitoring intelligent propulsé par Claude
Outils : santé système, endpoints HTTP, logs, anomalies, alertes
"""

import os
import json
import time
import platform
import sqlite3
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import anthropic
import psutil
import httpx
from mcp.server.fastmcp import FastMCP

load_dotenv()

mcp = FastMCP("MCP Surveillance IA")

DB_PATH = Path(__file__).parent / "surveillance.db"


# ─────────────────────────────────────────────
# Base de données locale (historique)
# ─────────────────────────────────────────────

def _init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT NOT NULL,
            cpu_pct   REAL,
            ram_pct   REAL,
            disk_pct  REAL,
            net_sent  INTEGER,
            net_recv  INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            ts       TEXT NOT NULL,
            level    TEXT,
            source   TEXT,
            message  TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS endpoint_checks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT NOT NULL,
            url         TEXT,
            status_code INTEGER,
            latency_ms  REAL,
            ok          INTEGER
        )
    """)
    conn.commit()
    conn.close()


_init_db()


def _save_metric(cpu: float, ram: float, disk: float, sent: int, recv: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO metrics (ts,cpu_pct,ram_pct,disk_pct,net_sent,net_recv) VALUES (?,?,?,?,?,?)",
        (datetime.utcnow().isoformat(), cpu, ram, disk, sent, recv),
    )
    conn.commit()
    conn.close()


def _save_alert(level: str, source: str, message: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO alerts (ts,level,source,message) VALUES (?,?,?,?)",
        (datetime.utcnow().isoformat(), level, source, message),
    )
    conn.commit()
    conn.close()


def get_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY manquante dans .env")
    return anthropic.Anthropic(api_key=api_key)


# ─────────────────────────────────────────────
# Outils MCP
# ─────────────────────────────────────────────

@mcp.tool()
def get_system_metrics() -> str:
    """
    Récupère les métriques système en temps réel (CPU, RAM, disque, réseau, processus).
    Enregistre les données dans la base locale pour historique.
    """
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    temps = {}
    try:
        sensor_temps = psutil.sensors_temperatures()
        if sensor_temps:
            for name, entries in sensor_temps.items():
                if entries:
                    temps[name] = round(entries[0].current, 1)
    except (AttributeError, OSError):
        pass

    # Top 5 processus par CPU
    top_procs = []
    for p in sorted(psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
                    key=lambda x: x.info["cpu_percent"] or 0, reverse=True)[:5]:
        top_procs.append({
            "pid": p.info["pid"],
            "name": p.info["name"],
            "cpu_pct": p.info["cpu_percent"],
            "mem_pct": round(p.info["memory_percent"] or 0, 2),
        })

    metrics = {
        "timestamp": datetime.utcnow().isoformat(),
        "platform": platform.system(),
        "cpu": {
            "percent": cpu,
            "cores_logical": psutil.cpu_count(),
            "cores_physical": psutil.cpu_count(logical=False),
            "freq_mhz": round(psutil.cpu_freq().current, 1) if psutil.cpu_freq() else None,
        },
        "ram": {
            "total_gb": round(ram.total / 1e9, 2),
            "used_gb": round(ram.used / 1e9, 2),
            "available_gb": round(ram.available / 1e9, 2),
            "percent": ram.percent,
        },
        "disk": {
            "total_gb": round(disk.total / 1e9, 2),
            "used_gb": round(disk.used / 1e9, 2),
            "free_gb": round(disk.free / 1e9, 2),
            "percent": disk.percent,
        },
        "network": {
            "bytes_sent_mb": round(net.bytes_sent / 1e6, 2),
            "bytes_recv_mb": round(net.bytes_recv / 1e6, 2),
            "packets_sent": net.packets_sent,
            "packets_recv": net.packets_recv,
        },
        "temperatures": temps,
        "top_processes": top_procs,
    }

    _save_metric(cpu, ram.percent, disk.percent, net.bytes_sent, net.bytes_recv)
    return json.dumps(metrics, ensure_ascii=False, indent=2)


@mcp.tool()
def check_endpoint(
    url: str,
    expected_status: int = 200,
    timeout_seconds: float = 10.0,
) -> str:
    """
    Vérifie la disponibilité et la latence d'un endpoint HTTP/HTTPS.

    Args:
        url: URL à vérifier (ex: https://api.example.com/health).
        expected_status: Code HTTP attendu (défaut : 200).
        timeout_seconds: Délai maximum en secondes.
    """
    start = time.perf_counter()
    ok = False
    status_code = 0
    error_msg = ""

    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            resp = client.get(url)
            status_code = resp.status_code
            ok = status_code == expected_status
    except httpx.TimeoutException:
        error_msg = "Timeout"
    except httpx.ConnectError as e:
        error_msg = f"Connexion refusée : {e}"
    except Exception as e:
        error_msg = str(e)

    latency_ms = round((time.perf_counter() - start) * 1000, 2)

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO endpoint_checks (ts,url,status_code,latency_ms,ok) VALUES (?,?,?,?,?)",
        (datetime.utcnow().isoformat(), url, status_code, latency_ms, int(ok)),
    )
    conn.commit()
    conn.close()

    result = {
        "url": url,
        "ok": ok,
        "status_code": status_code,
        "expected_status": expected_status,
        "latency_ms": latency_ms,
        "error": error_msg,
        "timestamp": datetime.utcnow().isoformat(),
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def analyze_logs_with_ai(log_content: str, context: str = "") -> str:
    """
    Analyse un extrait de logs avec Claude pour détecter erreurs, patterns et anomalies.

    Args:
        log_content: Contenu brut des logs (max ~4000 lignes).
        context: Contexte applicatif optionnel (ex: "API Node.js en production").
    """
    ctx = f"Contexte : {context}\n\n" if context else ""
    prompt = f"""{ctx}Analyse les logs suivants en tant qu'expert en surveillance système :

{log_content[:8000]}

Identifie :
1. Les erreurs critiques et leurs causes probables
2. Les patterns suspects ou anomalies
3. La tendance générale (dégradation ? récupération ?)
4. Les actions correctives recommandées par ordre de priorité
5. Un score de santé global (0-100)"""

    client = get_client()
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "text":
            return json.dumps({
                "analysis": block.text,
                "log_lines_analyzed": len(log_content.split("\n")),
                "timestamp": datetime.utcnow().isoformat(),
            }, ensure_ascii=False, indent=2)
    return "{}"


@mcp.tool()
def detect_anomalies(metrics_history_json: str) -> str:
    """
    Détecte des anomalies dans une série temporelle de métriques via Claude.

    Args:
        metrics_history_json: Liste JSON de métriques
            [{"ts": "...", "cpu_pct": 45, "ram_pct": 60, ...}, ...]
    """
    try:
        history = json.loads(metrics_history_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "JSON invalide"})

    prompt = f"""Tu es un expert en détection d'anomalies pour les systèmes informatiques.
Voici l'historique de métriques système :

{json.dumps(history, indent=2, ensure_ascii=False)}

Analyse et détecte :
1. Les anomalies statistiques (pics, creux, tendances inhabituelles)
2. Les corrélations suspectes entre métriques
3. Les fenêtres temporelles problématiques
4. La probabilité d'incident dans les prochaines heures (%)
5. Les recommandations immédiates et préventives

Format ta réponse de façon structurée avec des sections claires."""

    client = get_client()
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "text":
            return json.dumps({
                "anomaly_analysis": block.text,
                "data_points_analyzed": len(history),
                "timestamp": datetime.utcnow().isoformat(),
            }, ensure_ascii=False, indent=2)
    return "{}"


@mcp.tool()
def get_health_report() -> str:
    """
    Génère un rapport de santé complet du système avec recommandations IA.
    Combine métriques temps réel + historique + analyse Claude.
    """
    # Métriques actuelles
    current_raw = get_system_metrics()
    current = json.loads(current_raw)

    # Historique des 20 dernières mesures
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT ts,cpu_pct,ram_pct,disk_pct FROM metrics ORDER BY id DESC LIMIT 20"
    ).fetchall()
    alerts = conn.execute(
        "SELECT ts,level,source,message FROM alerts ORDER BY id DESC LIMIT 10"
    ).fetchall()
    endpoint_rows = conn.execute(
        "SELECT url, COUNT(*) as checks, SUM(ok) as ok_count, AVG(latency_ms) as avg_latency "
        "FROM endpoint_checks GROUP BY url ORDER BY checks DESC LIMIT 10"
    ).fetchall()
    conn.close()

    history = [
        {"ts": r[0], "cpu_pct": r[1], "ram_pct": r[2], "disk_pct": r[3]}
        for r in rows
    ]
    recent_alerts = [
        {"ts": a[0], "level": a[1], "source": a[2], "message": a[3]}
        for a in alerts
    ]
    endpoint_summary = [
        {"url": r[0], "checks": r[1], "uptime_pct": round(r[2] / r[1] * 100, 1),
         "avg_latency_ms": round(r[3], 1)}
        for r in endpoint_rows
    ]

    # Alertes automatiques
    auto_alerts = []
    if current["cpu"]["percent"] > 85:
        auto_alerts.append({"level": "CRITICAL", "message": f"CPU à {current['cpu']['percent']}%"})
        _save_alert("CRITICAL", "cpu", f"CPU à {current['cpu']['percent']}%")
    if current["ram"]["percent"] > 90:
        auto_alerts.append({"level": "CRITICAL", "message": f"RAM à {current['ram']['percent']}%"})
        _save_alert("CRITICAL", "ram", f"RAM à {current['ram']['percent']}%")
    if current["disk"]["percent"] > 85:
        auto_alerts.append({"level": "WARNING", "message": f"Disque à {current['disk']['percent']}%"})

    prompt = f"""Génère un rapport de santé système professionnel basé sur ces données :

Métriques actuelles : {json.dumps(current, indent=2)}
Historique récent : {json.dumps(history[:10], indent=2)}
Alertes actives : {json.dumps(auto_alerts, indent=2)}
Disponibilité endpoints : {json.dumps(endpoint_summary, indent=2)}

Le rapport doit inclure :
1. Score de santé global (0-100) avec justification
2. Statut de chaque composant (CPU/RAM/Disque/Réseau) : OK / WARNING / CRITICAL
3. Tendances observées
4. Actions recommandées (par priorité)
5. Prévision sur les 24 prochaines heures"""

    client = get_client()
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )

    report_text = ""
    for block in response.content:
        if block.type == "text":
            report_text = block.text
            break

    return json.dumps({
        "report": report_text,
        "current_metrics": current,
        "auto_alerts": auto_alerts,
        "recent_alerts": recent_alerts,
        "endpoint_availability": endpoint_summary,
        "generated_at": datetime.utcnow().isoformat(),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def send_webhook_alert(
    webhook_url: str,
    level: str,
    title: str,
    message: str,
) -> str:
    """
    Envoie une alerte via webhook (Slack, Discord, Teams, ou tout endpoint HTTP POST).

    Args:
        webhook_url: URL du webhook.
        level: Niveau d'alerte — INFO, WARNING, CRITICAL.
        title: Titre de l'alerte.
        message: Corps du message.
    """
    colors = {"INFO": "#36a64f", "WARNING": "#ff9800", "CRITICAL": "#f44336"}
    payload = {
        "text": f"*[{level}]* {title}",
        "attachments": [{
            "color": colors.get(level, "#888"),
            "text": message,
            "footer": f"MCP Surveillance IA • {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        }],
    }
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(webhook_url, json=payload)
            success = resp.status_code < 300
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

    _save_alert(level, "webhook", f"{title}: {message}")
    return json.dumps({
        "success": success,
        "webhook_url": webhook_url,
        "level": level,
        "title": title,
    })


if __name__ == "__main__":
    mcp.run()
