"""
MCP Finance & Trading — Analyse financière propulsée par Claude
Outils : cours, indicateurs techniques, signaux, portefeuille, news
"""

import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import anthropic
import yfinance as yf
import pandas as pd
from mcp.server.fastmcp import FastMCP

load_dotenv()

mcp = FastMCP("MCP Finance IA")


def get_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY manquante dans .env")
    return anthropic.Anthropic(api_key=api_key)


def _fetch_history(symbol: str, period: str = "3mo") -> pd.DataFrame:
    """Récupère l'historique d'un ticker via yfinance."""
    ticker = yf.Ticker(symbol.upper())
    df = ticker.history(period=period)
    if df.empty:
        raise ValueError(f"Aucune donnée pour le symbole '{symbol}'")
    return df


# ─────────────────────────────────────────────
# Outils MCP
# ─────────────────────────────────────────────

@mcp.tool()
def get_stock_price(symbol: str) -> str:
    """
    Retourne le cours actuel d'une action, ETF ou crypto.

    Args:
        symbol: Symbole boursier (ex: AAPL, TSLA, BTC-USD, EURUSD=X).
    """
    ticker = yf.Ticker(symbol.upper())
    info = ticker.fast_info
    price = info.last_price
    prev_close = info.previous_close
    change = price - prev_close
    pct = (change / prev_close) * 100 if prev_close else 0

    return json.dumps({
        "symbol": symbol.upper(),
        "price": round(price, 4),
        "previous_close": round(prev_close, 4),
        "change": round(change, 4),
        "change_pct": round(pct, 2),
        "currency": info.currency,
        "timestamp": datetime.utcnow().isoformat(),
    }, ensure_ascii=False)


@mcp.tool()
def get_technical_indicators(symbol: str, period: str = "3mo") -> str:
    """
    Calcule les principaux indicateurs techniques : RSI, MACD, Bollinger Bands, SMA, EMA.

    Args:
        symbol: Symbole boursier (ex: AAPL).
        period: Période d'historique — 1mo, 3mo, 6mo, 1y, 2y, 5y.
    """
    df = _fetch_history(symbol, period)
    close = df["Close"]

    # SMA / EMA
    sma_20 = close.rolling(20).mean().iloc[-1]
    sma_50 = close.rolling(50).mean().iloc[-1]
    ema_12 = close.ewm(span=12, adjust=False).mean().iloc[-1]
    ema_26 = close.ewm(span=26, adjust=False).mean().iloc[-1]

    # MACD
    macd_line = ema_12 - ema_26
    signal_line = (close.ewm(span=12, adjust=False).mean()
                   - close.ewm(span=26, adjust=False).mean()
                   ).ewm(span=9, adjust=False).mean().iloc[-1]

    # RSI (14 périodes)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    rsi = (100 - 100 / (1 + rs)).iloc[-1]

    # Bollinger Bands (20, 2σ)
    std20 = close.rolling(20).std().iloc[-1]
    bb_upper = sma_20 + 2 * std20
    bb_lower = sma_20 - 2 * std20
    current_price = close.iloc[-1]

    return json.dumps({
        "symbol": symbol.upper(),
        "current_price": round(current_price, 4),
        "sma_20": round(sma_20, 4),
        "sma_50": round(sma_50, 4),
        "ema_12": round(ema_12, 4),
        "ema_26": round(ema_26, 4),
        "macd": round(macd_line, 4),
        "macd_signal": round(signal_line, 4),
        "macd_histogram": round(macd_line - signal_line, 4),
        "rsi_14": round(rsi, 2),
        "bollinger_upper": round(bb_upper, 4),
        "bollinger_middle": round(sma_20, 4),
        "bollinger_lower": round(bb_lower, 4),
        "period": period,
    }, ensure_ascii=False)


@mcp.tool()
def get_trading_signal(symbol: str) -> str:
    """
    Génère un signal de trading (ACHETER / VENDRE / CONSERVER) basé sur
    les indicateurs techniques et l'analyse Claude.

    Args:
        symbol: Symbole boursier (ex: AAPL, BTC-USD).
    """
    indicators_raw = get_technical_indicators(symbol, period="3mo")
    indicators = json.loads(indicators_raw)

    prompt = f"""Tu es un expert en analyse technique financière.
Voici les indicateurs techniques pour {symbol} :

{json.dumps(indicators, indent=2, ensure_ascii=False)}

Sur la base de ces indicateurs, donne :
1. Un signal clair : ACHETER / VENDRE / CONSERVER
2. Un niveau de confiance (1-10)
3. Les 3 raisons principales de ce signal
4. Les risques à surveiller
5. Les niveaux clés de support et résistance

Sois précis et actionnable. Rappelle toujours que ce n'est pas un conseil financier."""

    client = get_client()
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "text":
            return json.dumps({
                "symbol": symbol.upper(),
                "analysis": block.text,
                "indicators_snapshot": indicators,
                "generated_at": datetime.utcnow().isoformat(),
            }, ensure_ascii=False, indent=2)
    return "{}"


@mcp.tool()
def analyze_portfolio(portfolio_json: str) -> str:
    """
    Analyse un portefeuille d'actions et fournit des recommandations.

    Args:
        portfolio_json: JSON de la forme
            [{"symbol": "AAPL", "quantity": 10, "avg_price": 150.0}, ...]
    """
    portfolio = json.loads(portfolio_json)
    results = []
    total_value = 0.0
    total_cost = 0.0

    for pos in portfolio:
        symbol = pos["symbol"].upper()
        qty = pos["quantity"]
        avg = pos["avg_price"]

        ticker = yf.Ticker(symbol)
        current_price = ticker.fast_info.last_price
        cost = qty * avg
        value = qty * current_price
        pnl = value - cost
        pnl_pct = (pnl / cost * 100) if cost else 0

        total_value += value
        total_cost += cost
        results.append({
            "symbol": symbol,
            "quantity": qty,
            "avg_price": round(avg, 4),
            "current_price": round(current_price, 4),
            "cost_basis": round(cost, 2),
            "current_value": round(value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
        })

    total_pnl = total_value - total_cost
    summary = {
        "positions": results,
        "total_cost": round(total_cost, 2),
        "total_value": round(total_value, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round((total_pnl / total_cost * 100) if total_cost else 0, 2),
    }

    prompt = f"""Tu es un gestionnaire de portefeuille expert.
Voici le portefeuille à analyser :

{json.dumps(summary, indent=2, ensure_ascii=False)}

Fournis :
1. Un bilan global du portefeuille
2. Les positions les plus performantes et les plus risquées
3. La diversification (secteurs, géographie, type d'actifs)
4. Des recommandations d'optimisation
5. Les risques principaux à surveiller"""

    client = get_client()
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "text":
            summary["claude_analysis"] = block.text
            break

    return json.dumps(summary, ensure_ascii=False, indent=2)


@mcp.tool()
def get_financial_news_sentiment(topic: str) -> str:
    """
    Récupère les actualités financières sur un sujet et en analyse le sentiment via Claude.

    Args:
        topic: Sujet financier (ex: Apple, Bitcoin, Fed, inflation, marchés émergents).
    """
    ticker_map = {
        "apple": "AAPL", "tesla": "TSLA", "nvidia": "NVDA",
        "bitcoin": "BTC-USD", "microsoft": "MSFT", "google": "GOOGL",
    }
    sym = ticker_map.get(topic.lower(), topic.upper())
    ticker = yf.Ticker(sym)
    news_items = ticker.news[:10] if ticker.news else []

    headlines = [
        {"title": n.get("title", ""), "publisher": n.get("publisher", ""),
         "link": n.get("link", "")}
        for n in news_items
    ]

    prompt = f"""Voici les dernières actualités financières sur '{topic}' :

{json.dumps(headlines, indent=2, ensure_ascii=False)}

Analyse :
1. Le sentiment global (Positif / Neutre / Négatif) avec score -10 à +10
2. Les thèmes dominants dans ces actualités
3. L'impact potentiel sur le cours
4. Ce que les investisseurs devraient surveiller"""

    client = get_client()
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "text":
            return json.dumps({
                "topic": topic,
                "headlines": headlines,
                "sentiment_analysis": block.text,
                "timestamp": datetime.utcnow().isoformat(),
            }, ensure_ascii=False, indent=2)
    return "{}"


@mcp.tool()
def backtest_simple_strategy(
    symbol: str,
    strategy: str = "sma_crossover",
    period: str = "1y",
) -> str:
    """
    Effectue un backtest simplifié d'une stratégie sur l'historique.

    Args:
        symbol: Symbole boursier (ex: AAPL).
        strategy: Stratégie — 'sma_crossover' (SMA 20/50) | 'rsi_mean_reversion'.
        period: Période — 6mo, 1y, 2y.
    """
    df = _fetch_history(symbol, period)
    close = df["Close"].copy()
    signals = pd.Series(0, index=close.index)

    if strategy == "sma_crossover":
        sma_short = close.rolling(20).mean()
        sma_long = close.rolling(50).mean()
        signals[sma_short > sma_long] = 1
        signals[sma_short < sma_long] = -1
    elif strategy == "rsi_mean_reversion":
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rsi = 100 - 100 / (1 + gain / loss)
        signals[rsi < 30] = 1
        signals[rsi > 70] = -1

    returns = close.pct_change()
    strategy_returns = signals.shift(1) * returns
    cumulative = (1 + strategy_returns).cumprod()
    total_return = (cumulative.iloc[-1] - 1) * 100
    buy_hold = (close.iloc[-1] / close.iloc[0] - 1) * 100

    result = {
        "symbol": symbol.upper(),
        "strategy": strategy,
        "period": period,
        "strategy_return_pct": round(total_return, 2),
        "buy_hold_return_pct": round(buy_hold, 2),
        "outperformance_pct": round(total_return - buy_hold, 2),
        "total_trades": int((signals.diff() != 0).sum()),
        "start_date": str(df.index[0].date()),
        "end_date": str(df.index[-1].date()),
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
