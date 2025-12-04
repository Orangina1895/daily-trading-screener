import yfinance as yf
import pandas as pd
import requests
import os
from datetime import datetime, timedelta

# ================================
# ✅ CONFIG
# ================================
START = "2022-01-01"
END = datetime.now().strftime("%Y-%m-%d")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

POSITIONS_FILE = "positions.csv"

# ================================
# ✅ NASDAQ TOP 500 (DYNAMISCH + FALLBACK)
# ================================
def load_nasdaq_top_500():
    try:
        print("Lade Nasdaq Top 500 dynamisch...")
        url = "https://www.nasdaq.com/api/screener/stocks?tableonly=true&limit=500"
        data = requests.get(url, timeout=10).json()
        tickers = [row["symbol"] for row in data["rows"]]
        print("Nasdaq Top 500 geladen:", len(tickers))
        return tickers
    except:
        print("Dynamischer Nasdaq-Download fehlgeschlagen – Fallback aktiv.")
        return ["NVDA","AAPL","MSFT","GOOG","GOOGL","AMZN","META","TSLA","AVGO",
                "ASML","NFLX","PLTR","COST","AMD","ADBE","ADI"]

tickers = load_nasdaq_top_500()

# ================================
# ✅ POSITIONEN LADEN
# ================================
if os.path.exists(POSITIONS_FILE):
    positions = pd.read_csv(POSITIONS_FILE, index_col=0)["in_position"].to_dict()
else:
    positions = {}

def in_position(ticker):
    return positions.get(ticker, False)

def save_positions():
    pd.DataFrame.from_dict(positions, orient="index", columns=["in_position"]).to_csv(POSITIONS_FILE)

# ================================
# ✅ SIGNAL LOGIK
# ================================
signals = []

for TICKER in tickers:
    try:
        df = yf.download(TICKER, start=START, end=END, progress=False)

        if df.empty or len(df) < 250:
            continue

        df["EMA20"] = df["Close"].ewm(span=20).mean()
        df["EMA50"] = df["Close"].ewm(span=50).mean()
        df["EMA200"] = df["Close"].ewm(span=200).mean()

        yesterday = df.iloc[-2]
        day_before = df.iloc[-3]

        entry = (
            yesterday["EMA20"] > yesterday["EMA50"] > yesterday["EMA200"]
            and not (day_before["EMA20"] > day_before["EMA50"] > day_before["EMA200"])
        )

        exit_sig = (
            yesterday["Close"] < yesterday["EMA200"]
            and day_before["Close"] >= day_before["EMA200"]
        )

        tp1 = yesterday["Close"] > 1.10 * day_before["Close"]
        tp2 = yesterday["Close"] > 1.20 * day_before["Close"]

        if entry and not in_position(TICKER):
            signals.append([TICKER, "ENTRY"])
            positions[TICKER] = True

        elif tp2 and in_position(TICKER):
            signals.append([TICKER, "TP2"])

        elif tp1 and in_position(TICKER):
            signals.append([TICKER, "TP1"])

        elif exit_sig and in_position(TICKER):
            signals.append([TICKER, "EXIT"])
            positions[TICKER] = False

    except Exception as e:
        print("Fehler bei:", TICKER, e)

save_positions()

signals_df = pd.DataFrame(signals, columns=["Ticker", "Neues Signal"])

# ================================
# ✅ FEAR & GREED INDEX
# ================================
try:
    fg = requests.get("https://api.alternative.me/fng/").json()
    fear_greed_value = fg["data"][0]["value"]
except:
    fear_greed_value = None

# ================================
# ✅ NASDAQ-100 PERFORMANCE
# ================================
try:
    ndx = yf.download("^NDX", period="5d", progress=False)
    nasdaq_perf = (ndx["Close"].iloc[-1] / ndx["Close"].iloc[-2] - 1) * 100
except:
    nasdaq_perf = 0.0

# ================================
# ✅ TELEGRAM FORMAT
# ================================
entry_list = signals_df[signals_df["Neues Signal"] == "ENTRY"]["Ticker"].tolist()
tp1_list   = signals_df[signals_df["Neues Signal"] == "TP1"]["Ticker"].tolist()
tp2_list   = signals_df[signals_df["Neues Signal"] == "TP2"]["Ticker"].tolist()
exit_list  = signals_df[signals_df["Neues Signal"] == "EXIT"]["Ticker"].tolist()

text = "📊 *TÄGLICHE SIGNALAUSWERTUNG*\n\n"
text += f"😱 *Fear & Greed:* {fear_greed_value if fear_greed_value else 'Nicht verfügbar'}\n"
text += f"📉 *Nasdaq-100 gestern:* {nasdaq_perf:+.2f} %\n\n"

text += "🚀 *ENTRY Signale:*\n"
text += "\n".join([f"• {t}" for t in entry_list]) if entry_list else "Keine"
text += "\n\n🎯 *TP1:*\n"
text += "\n".join([f"• {t}" for t in tp1_list]) if tp1_list else "Keine"
text += "\n\n🏁 *TP2:*\n"
text += "\n".join([f"• {t}" for t in tp2_list]) if tp2_list else "Keine"
text += "\n\n❤️ *EXIT Signale:*\n"
text += "\n".join([f"• {t}" for t in exit_list]) if exit_list else "Keine"

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

print("====================================")
print("GLOBAL-SCREENER FERTIG")
print("Signale:", len(signals_df))
print("====================================")
