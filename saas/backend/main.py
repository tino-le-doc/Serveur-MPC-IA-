"""
SaaS MCP IA — Backend FastAPI
API REST + intégration MCP Finance & Surveillance + SQLite
"""

import os
import sqlite3
import json
import hashlib
import secrets
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import anthropic
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="MCP IA SaaS", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = Path(__file__).parent.parent / "saas.db"
FRONTEND_PATH = Path(__file__).parent.parent / "frontend"


# ─────────────────────────────────────────────
# Base de données
# ─────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            email      TEXT UNIQUE NOT NULL,
            name       TEXT,
            api_token  TEXT UNIQUE,
            plan       TEXT DEFAULT 'free',
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS queries (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            tool       TEXT,
            input      TEXT,
            output     TEXT,
            tokens     INTEGER,
            created_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            level      TEXT,
            title      TEXT,
            message    TEXT,
            read       INTEGER DEFAULT 0,
            created_at TEXT
        );
    """)
    conn.commit()
    conn.close()


init_db()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def get_client():
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


# ─────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────

def require_auth(authorization: str = Header(None), db: sqlite3.Connection = Depends(get_db)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token manquant")
    token = authorization.split(" ", 1)[1]
    row = db.execute("SELECT * FROM users WHERE api_token = ?", (token,)).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Token invalide")
    return dict(row)


# ─────────────────────────────────────────────
# Modèles Pydantic
# ─────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    name: str


class AskRequest(BaseModel):
    question: str
    system_prompt: str = ""


class StockRequest(BaseModel):
    symbol: str


class PortfolioRequest(BaseModel):
    positions: list  # [{"symbol": "AAPL", "quantity": 10, "avg_price": 150}]


class AlertRequest(BaseModel):
    level: str
    title: str
    message: str


# ─────────────────────────────────────────────
# Routes — Auth
# ─────────────────────────────────────────────

@app.post("/api/register")
def register(req: RegisterRequest, db: sqlite3.Connection = Depends(get_db)):
    token = secrets.token_hex(32)
    try:
        db.execute(
            "INSERT INTO users (email, name, api_token, plan, created_at) VALUES (?,?,?,?,?)",
            (req.email, req.name, token, "free", datetime.utcnow().isoformat()),
        )
        db.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Email déjà enregistré")
    return {"message": "Compte créé", "api_token": token, "plan": "free"}


@app.post("/api/login")
def login(req: RegisterRequest, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM users WHERE email = ?", (req.email,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return {"api_token": row["api_token"], "name": row["name"], "plan": row["plan"]}


# ─────────────────────────────────────────────
# Routes — IA Claude
# ─────────────────────────────────────────────

@app.post("/api/ask")
def ask_claude(
    req: AskRequest,
    user=Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
):
    client = get_client()
    kwargs = {
        "model": "claude-opus-4-6",
        "max_tokens": 4096,
        "thinking": {"type": "adaptive"},
        "messages": [{"role": "user", "content": req.question}],
    }
    if req.system_prompt:
        kwargs["system"] = req.system_prompt

    response = client.messages.create(**kwargs)
    answer = ""
    for block in response.content:
        if block.type == "text":
            answer = block.text
            break

    tokens = response.usage.input_tokens + response.usage.output_tokens
    db.execute(
        "INSERT INTO queries (user_id,tool,input,output,tokens,created_at) VALUES (?,?,?,?,?,?)",
        (user["id"], "ask_claude", req.question, answer, tokens, datetime.utcnow().isoformat()),
    )
    db.commit()
    return {"answer": answer, "tokens_used": tokens}


@app.post("/api/finance/quote")
def get_quote(req: StockRequest, user=Depends(require_auth)):
    try:
        import yfinance as yf
        ticker = yf.Ticker(req.symbol.upper())
        info = ticker.fast_info
        return {
            "symbol": req.symbol.upper(),
            "price": round(info.last_price, 4),
            "previous_close": round(info.previous_close, 4),
            "change_pct": round((info.last_price - info.previous_close) / info.previous_close * 100, 2),
            "currency": info.currency,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/finance/analyze")
def analyze_stock(
    req: StockRequest,
    user=Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
):
    try:
        import yfinance as yf
        import pandas as pd

        df = yf.Ticker(req.symbol.upper()).history(period="3mo")
        if df.empty:
            raise HTTPException(status_code=404, detail=f"Symbole '{req.symbol}' introuvable")

        close = df["Close"]
        current_price = close.iloc[-1]
        sma_20 = close.rolling(20).mean().iloc[-1]
        sma_50 = close.rolling(50).mean().iloc[-1]
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rsi = (100 - 100 / (1 + gain / loss)).iloc[-1]

        indicators = {
            "symbol": req.symbol.upper(),
            "price": round(current_price, 2),
            "sma_20": round(sma_20, 2),
            "sma_50": round(sma_50, 2),
            "rsi": round(rsi, 2),
        }

        prompt = (
            f"Analyse rapide de {req.symbol.upper()} :\n{json.dumps(indicators)}\n\n"
            "Donne un signal (ACHETER/VENDRE/CONSERVER), 3 raisons, et les risques. Sois concis."
        )

        client = get_client()
        resp = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        analysis = ""
        for block in resp.content:
            if block.type == "text":
                analysis = block.text
                break

        db.execute(
            "INSERT INTO queries (user_id,tool,input,output,tokens,created_at) VALUES (?,?,?,?,?,?)",
            (user["id"], "analyze_stock", req.symbol,
             analysis, resp.usage.input_tokens + resp.usage.output_tokens,
             datetime.utcnow().isoformat()),
        )
        db.commit()
        return {"indicators": indicators, "analysis": analysis}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/finance/portfolio")
def analyze_portfolio(
    req: PortfolioRequest,
    user=Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
):
    try:
        import yfinance as yf
        results = []
        for pos in req.positions:
            t = yf.Ticker(pos["symbol"].upper())
            price = t.fast_info.last_price
            cost = pos["quantity"] * pos["avg_price"]
            value = pos["quantity"] * price
            results.append({
                "symbol": pos["symbol"].upper(),
                "quantity": pos["quantity"],
                "avg_price": pos["avg_price"],
                "current_price": round(price, 2),
                "pnl": round(value - cost, 2),
                "pnl_pct": round((value - cost) / cost * 100, 2),
            })
        total_value = sum(r["current_price"] * r["quantity"] for r in results)
        return {"positions": results, "total_value": round(total_value, 2)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
# Routes — Surveillance
# ─────────────────────────────────────────────

@app.get("/api/system/metrics")
def system_metrics(user=Depends(require_auth)):
    import psutil
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "cpu_pct": cpu,
        "ram_pct": ram.percent,
        "ram_used_gb": round(ram.used / 1e9, 2),
        "ram_total_gb": round(ram.total / 1e9, 2),
        "disk_pct": disk.percent,
        "disk_free_gb": round(disk.free / 1e9, 2),
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/api/alerts")
def create_alert(
    req: AlertRequest,
    user=Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
):
    db.execute(
        "INSERT INTO alerts (user_id,level,title,message,created_at) VALUES (?,?,?,?,?)",
        (user["id"], req.level, req.title, req.message, datetime.utcnow().isoformat()),
    )
    db.commit()
    return {"message": "Alerte créée"}


@app.get("/api/alerts")
def list_alerts(
    user=Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
):
    rows = db.execute(
        "SELECT * FROM alerts WHERE user_id = ? ORDER BY id DESC LIMIT 50",
        (user["id"],),
    ).fetchall()
    return {"alerts": [dict(r) for r in rows]}


# ─────────────────────────────────────────────
# Routes — Dashboard & Stats
# ─────────────────────────────────────────────

@app.get("/api/stats")
def get_stats(
    user=Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
):
    queries_count = db.execute(
        "SELECT COUNT(*) FROM queries WHERE user_id = ?", (user["id"],)
    ).fetchone()[0]
    tokens_used = db.execute(
        "SELECT COALESCE(SUM(tokens), 0) FROM queries WHERE user_id = ?", (user["id"],)
    ).fetchone()[0]
    alerts_count = db.execute(
        "SELECT COUNT(*) FROM alerts WHERE user_id = ? AND read = 0", (user["id"],)
    ).fetchone()[0]
    recent = db.execute(
        "SELECT tool, created_at FROM queries WHERE user_id = ? ORDER BY id DESC LIMIT 5",
        (user["id"],),
    ).fetchall()
    return {
        "user": {"name": user["name"], "plan": user["plan"]},
        "queries_total": queries_count,
        "tokens_used": tokens_used,
        "unread_alerts": alerts_count,
        "recent_activity": [dict(r) for r in recent],
    }


# ─────────────────────────────────────────────
# Serve frontend
# ─────────────────────────────────────────────

@app.get("/")
def root():
    return FileResponse(FRONTEND_PATH / "dashboard.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
