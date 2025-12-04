import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timedelta

# ================================
# ✅ EINSTELLUNGEN
# ================================
START = "1990-01-01"
END = datetime.today().strftime("%Y-%m-%d")

import os

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")


# ================================
# ✅ NASDAQ TOP 500 LADEN
# ================================
print("Lade Nasdaq Top 500...")

nasdaq_url = "https://raw.githubusercontent.com/datasets/nasdaq-listings/master/data/nasdaq-listed-symbols.csv"
nasdaq_df = pd.read_csv(nasdaq_url)
tickers = nasdaq_df["Symbol"].dropna().unique().tolist()[:500]

print("Aktien geladen:", len(tickers))

# ================================
# ✅ POSITIONEN SPEICHERN
# ================================
positions = {}

def in_position(ticker):
    return positions.get(ticker, False)

# ================================
# ✅ SIGNAL LOGIK (FINAL & KORREKT)
# ================================
signals = []

for TICKER in tickers:
    try:
        df = yf.download(TICKER, start=START, end=END, progress=False, auto_adjust=True)

        if df.empty or len(df) < 250:
            continue

        # ✅ Indikatoren
        df["EMA20"] = df["Close"].ewm(span=20).mean()
        df["EMA50"] = df["Close"].ewm(span=50).mean()
        df["EMA200"] = df["Close"].ewm(span=200).mean()

        # ✅ WICHTIG: Serien synchronisieren (sonst FEHLER)
        df = df.dropna()

        if len(df) < 5:
            continue

        yesterday = df.iloc[-2]
        day_before = df.iloc[-3]

        # ================================
        # ✅ ENTRY (nur wenn gestern NEU)
        # ================================
        entry_today = (
            yesterday["EMA20"] > yesterday["EMA50"] > yesterday["EMA200"]
        )

        entry_yesterday = (
            day_before["EMA20"] > day_before["EMA50"] > day_before["EMA200"]
        )

        entry = entry_today and not entry_yesterday

        # ================================
        # ✅ EXIT (nur wenn vorher ENTRY)
        # ================================
        exit_sig = (
            yesterday["Close"] < yesterday["EMA200"]
            and day_before["Close"] >= day_before["EMA200"]
        )

        # ================================
        # ✅ TP1 / TP2 (nur wenn Position offen)
        # ================================
        tp1 = yesterday["Close"] >= 1.10 * day_before["Close"]
        tp2 = yesterday["Close"] >= 1.20 * day_before["Close"]

        # ================================
        # ✅ SIGNAL-AUSWAHL (saubere Reihenfolge)
        # ================================

        # ✅ ENTRY darf NIEMALS blockiert werden
        if entry:
            signals.append([TICKER, "ENTRY"])
            positions[TICKER] = True

        # ✅ TP2 nur wenn Position existiert
        elif tp2 and in_position(TICKER):
            signals.append([TICKER, "TP2"])

        # ✅ TP1 nur wenn Position existiert
        elif tp1 and in_position(TICKER):
            signals.append([TICKER, "TP1"])

        # ✅ EXIT nur wenn Position existiert
        elif exit_sig and in_position(TICKER):
            signals.append([TICKER, "EXIT"])
            positions[TICKER] = False

    except Exception as e:
        print("Fehler bei:", TICKER, e)


signals_df = pd.DataFrame(signals, columns=["Ticker", "Neues Signal"])


# ================================
# ✅ EXCEL EXPORT
# ================================
filename = f"daily_signals_{datetime.today().strftime('%Y-%m-%d')}.xlsx"
signals_df.to_excel(filename, index=False)

# ================================
# ✅ TELEGRAM FORMATIERUNG
# ================================
entry_list = signals_df[signals_df["Neues Signal"] == "ENTRY"]["Ticker"].tolist()
tp1_list = signals_df[signals_df["Neues Signal"] == "TP1"]["Ticker"].tolist()
tp2_list = signals_df[signals_df["Neues Signal"] == "TP2"]["Ticker"].tolist()
exit_list = signals_df[signals_df["Neues Signal"] == "EXIT"]["Ticker"].tolist()

text = "📊 *TÄGLICHER TRADING-SCREENER (GESTERN)*\n\n"

text += "🟢 *ENTRY Signale:*\n"
text += "\n".join(entry_list) if entry_list else "Keine"
text += "\n\n🟡 *TP1 Signale:*\n"
text += "\n".join(tp1_list) if tp1_list else "Keine"
text += "\n\n🟠 *TP2 Signale:*\n"
text += "\n".join(tp2_list) if tp2_list else "Keine"
text += "\n\n🔴 *EXIT Signale:*\n"
text += "\n".join(exit_list) if exit_list else "Keine"

# ================================
# ✅ TELEGRAM SENDEN
# ================================
url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
payload = {
    "chat_id": CHAT_ID,
    "text": text,
    "parse_mode": "Markdown"
}

requests.post(url, data=payload)

# ================================
# ✅ ABSCHLUSS
# ================================
print("====================================")
print("GLOBAL SCREENER FERTIG")
print("Signale:", len(signals_df))
print("Datei:", filename)
print("====================================")


