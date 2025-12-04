#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import datetime as dt

import pandas as pd
import yfinance as yf
import requests

# ============================================
# ✅ KONFIGURATION
# ============================================

# Zeitraum für Kursdaten (ausreichend für EMA200)
DATA_PERIOD = "260d"   # ca. 1 Jahr

# Telegram (Secrets müssen in GitHub Actions gesetzt sein)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID")

POSITIONS_FILE = "positions.json"


# ============================================
# ✅ HILFSFUNKTIONEN: TICKER-LISTE
# ============================================

def load_nasdaq_top_500():
    """
    Versucht, die Top ~500 NASDAQ-Aktien dynamisch zu laden.
    Falls das fehlschlägt, wird eine kleine Fallback-Liste zurückgegeben.
    """
    # 1) Falls CSV im Repo vorhanden ist, diese nutzen
    if os.path.exists("nasdaq_top_500.csv"):
        try:
            df = pd.read_csv("nasdaq_top_500.csv")
            tickers = df["Ticker"].dropna().unique().tolist()
            print(f"Nasdaq Top 500 aus CSV geladen: {len(tickers)}")
            return tickers
        except Exception as e:
            print("Fehler beim Lesen von nasdaq_top_500.csv:", e)

    # 2) Dynamisch von Nasdaq-Screener (kann gelegentlich scheitern)
    try:
        print("Lade Nasdaq Top 500 dynamisch...")
        url = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=500&exchange=nasdaq"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
        }
        r = requests.get(url, headers=headers, timeout=15)
        data = r.json()
        rows = data["data"]["rows"]
        tickers = [row["symbol"] for row in rows if row.get("symbol")]
        tickers = list(dict.fromkeys(tickers))  # Duplikate entfernen
        print("Nasdaq Top 500 geladen:", len(tickers))
        return tickers
    except Exception as e:
        print("Dynamischer Nasdaq-Download fehlgeschlagen:", e)
        print("Verwende kleine Fallback-Liste.")
        # 3) Minimal-Fallback
        return [
            "NVDA", "AAPL", "MSFT", "GOOG", "GOOGL", "AMZN", "META",
            "TSLA", "AVGO", "ASML", "NFLX", "PLTR", "COST", "AMD", "ADBE", "ADI"
        ]


# ============================================
# ✅ VIRTUELLES DEPOT (POSITIONSVERWALTUNG)
# ============================================

def load_positions(tickers):
    """
    Lädt positions.json, falls vorhanden, ansonsten initialisiert alle Ticker als 'nicht in Position'.
    Struktur: { "TICKER": {"in_position": bool, "tp1_hit": bool, "tp2_hit": bool} }
    """
    positions = {}
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r") as f:
                positions = json.load(f)
        except Exception as e:
            print("Fehler beim Laden von positions.json, initialisiere neu:", e)
            positions = {}

    # Sicherstellen, dass alle Ticker einen Eintrag haben
    for t in tickers:
        if t not in positions:
            positions[t] = {
                "in_position": False,
                "tp1_hit": False,
                "tp2_hit": False,
            }

    return positions


def save_positions(positions):
    try:
        with open(POSITIONS_FILE, "w") as f:
            json.dump(positions, f, indent=2)
    except Exception as e:
        print("Fehler beim Speichern von positions.json:", e)


def in_position(positions, ticker):
    return positions.get(ticker, {}).get("in_position", False)


# ============================================
# ✅ MARKTINFOS: FEAR & GREED + NASDAQ-100
# ============================================

def get_fear_greed():
    """
    CNN Fear & Greed Index als String 'Score – Rating'
    """
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        data = requests.get(url, timeout=10).json()
        score = data["fear_and_greed"]["score"]
        rating = data["fear_and_greed"]["rating"]
        return f"{score} – {rating}"
    except Exception as e:
        print("Fehler beim Abrufen des Fear & Greed Index:", e)
        return "Nicht verfügbar"


def get_nasdaq100_performance():
    """
    Performance des Nasdaq-100 (Ticker ^NDX) vom Vortag in %.
    """
    try:
        df = yf.download("^NDX", period="5d", interval="1d", progress=False, auto_adjust=True)
        if len(df) < 2:
            return None
        yesterday = df.iloc[-1]
        day_before = df.iloc[-2]
        change_pct = (yesterday["Close"] / day_before["Close"] - 1) * 100
        return round(change_pct, 2)
    except Exception as e:
        print("Fehler beim Abrufen der Nasdaq-100-Performance:", e)
        return None


# ============================================
# ✅ TELEGRAM
# ============================================

def send_telegram_message(text):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Kein TELEGRAM_TOKEN oder CHAT_ID gesetzt – Nachricht wird nicht gesendet.")
        print("Vorschau der Nachricht:")
        print(text)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        r = requests.post(url, data=payload, timeout=10)
        if r.status_code != 200:
            print("Fehler beim Senden an Telegram:", r.text)
    except Exception as e:
        print("Exception beim Senden an Telegram:", e)


# ============================================
# ✅ HAUPTLOGIK
# ============================================

def main():
    # Ticker laden
    tickers = load_nasdaq_top_500()

    # Virtuelles Depot laden
    positions = load_positions(tickers)

    # Signale sammeln
    signals = []

    # Für Debug / Logging
    today = dt.date.today()
    print("====================================")
    print("GLOBAL-SCREENER START")
    print("Datum:", today.isoformat())
    print("Anzahl Ticker:", len(tickers))
    print("====================================")

    for TICKER in tickers:
        try:
            df = yf.download(
                TICKER,
                period=DATA_PERIOD,
                interval="1d",
                progress=False,
                auto_adjust=False,
            )

            if df.empty or len(df) < 200:
                continue

            # EMAs berechnen
            df["EMA20"] = df["Close"].ewm(span=20).mean()
            df["EMA50"] = df["Close"].ewm(span=50).mean()
            df["EMA200"] = df["Close"].ewm(span=200).mean()

            # Wir nehmen die letzten beiden Tage (gestern & vorgestern)
            yesterday = df.iloc[-1]
            day_before = df.iloc[-2]

            # ENTRY-Bedingung:
            # gestern EMA20 > EMA50 > EMA200
            # UND vorgestern NICHT bereits EMA20 > EMA50 > EMA200 (Kaskaden-Start)
            entry = (
                (yesterday["EMA20"] > yesterday["EMA50"] > yesterday["EMA200"])
                and not (day_before["EMA20"] > day_before["EMA50"] > day_before["EMA200"])
            )

            # EXIT-Bedingung:
            # Close fällt gestern UNTER EMA200, am Vortag war er noch ÜBER/gleich EMA200
            exit_sig = (
                yesterday["Close"] < yesterday["EMA200"]
                and day_before["Close"] >= day_before["EMA200"]
            )

            # TP1: Close gestern > 10% über Vortag
            tp1 = yesterday["Close"] > 1.10 * day_before["Close"]

            # TP2: Close gestern > 20% über Vortag
            tp2 = yesterday["Close"] > 1.20 * day_before["Close"]

            pos = positions[TICKER]

            # =====================================
            # SIGNAL-LOGIK mit virtuellem Depot
            # =====================================

            # ENTRY nur, wenn aktuell nicht in Position
            if entry and not pos["in_position"]:
                signals.append([TICKER, "ENTRY"])
                pos["in_position"] = True
                pos["tp1_hit"] = False
                pos["tp2_hit"] = False

            # TP2 nur, wenn in Position und TP1 schon erreicht
            elif tp2 and pos["in_position"] and pos["tp1_hit"] and not pos["tp2_hit"]:
                signals.append([TICKER, "TP2"])
                pos["tp2_hit"] = True

            # TP1 nur, wenn in Position und TP1 noch NICHT erreicht
            elif tp1 and pos["in_position"] and not pos["tp1_hit"]:
                signals.append([TICKER, "TP1"])
                pos["tp1_hit"] = True

            # EXIT nur, wenn in Position
            elif exit_sig and pos["in_position"]:
                signals.append([TICKER, "EXIT"])
                pos["in_position"] = False
                pos["tp1_hit"] = False
                pos["tp2_hit"] = False

            positions[TICKER] = pos

        except Exception as e:
            print("Fehler bei:", TICKER, e)

    # Signale in DataFrame
    if signals:
        signals_df = pd.DataFrame(signals, columns=["Ticker", "Neues Signal"])
    else:
        signals_df = pd.DataFrame(columns=["Ticker", "Neues Signal"])

    # Depot speichern (nur sinnvoll, wenn das File zwischen Runs erhalten bleibt)
    save_positions(positions)

    # ============================================
    # ✅ TELEGRAM-NACHRICHT AUFBAUEN
    # ============================================

    fear_greed = get_fear_greed()
    nasdaq_perf = get_nasdaq100_performance()

    if len(signals_df) > 0:
        text = "📈 *NEUE TRADING-SIGNALE (GESTERN)*\n\n"

        entry_list = signals_df[signals_df["Neues Signal"] == "ENTRY"]["Ticker"].tolist()
        tp1_list   = signals_df[signals_df["Neues Signal"] == "TP1"]["Ticker"].tolist()
        tp2_list   = signals_df[signals_df["Neues Signal"] == "TP2"]["Ticker"].tolist()
        exit_list  = signals_df[signals_df["Neues Signal"] == "EXIT"]["Ticker"].tolist()

        if entry_list:
            text += "🟢 *ENTRY-SIGNALE*\n" + "\n".join(entry_list) + "\n\n"

        if tp1_list:
            text += "🟡 *TP1-SIGNALE*\n" + "\n".join(tp1_list) + "\n\n"

        if tp2_list:
            text += "🟠 *TP2-SIGNALE*\n" + "\n".join(tp2_list) + "\n\n"

        if exit_list:
            text += "🔴 *EXIT-SIGNALE*\n" + "\n".join(exit_list) + "\n\n"

    else:
        text = "✅ Keine neuen Signale gestern.\n\n"

    # Marktinfos anhängen
    text += "────────────────────\n"
    text += f"😨 *Fear & Greed Index:* {fear_greed}\n"
    if nasdaq_perf is not None:
        text += f"📊 *Nasdaq-100 gestern:* {nasdaq_perf:+.2f} %\n"

    # Telegram senden
    send_telegram_message(text)

    # Konsolen-Log
    print("====================================")
    print("GLOBAL-SCREENER FERTIG")
    print("Signale:", len(signals_df))
    print("====================================")


if __name__ == "__main__":
    main()
