import yfinance as yf
import pandas as pd
import requests
import os
from datetime import datetime

# ================================
# ✅ SETTINGS
# ================================
START = "2023-01-01"
END = datetime.today().strftime("%Y-%m-%d")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# ================================
# ✅ TICKER LISTE (STABILER FALLBACK)
# ================================
tickers = [
    "NVDA","AAPL","MSFT","GOOG","GOOGL","AMZN","META","TSLA","AVGO","ASML",
    "NFLX","PLTR","COST","AMD","ADBE","ADI"
]

# ================================
# ✅ POSITION TRACKING (virtuell)
# ================================
positions = {}

def in_position(ticker):
    return positions.get(ticker, False)

# ================================
# ✅ SIGNALERKENNUNG
# ================================
signals = []
checked_count = 0

for TICKER in tickers:
    try:
        checked_count += 1

        df = yf.download(TICKER, start=START, end=END, progress=False)

        if df.empty or len(df) < 250:
            continue

        df["EMA20"] = df["Close"].ewm(span=20).mean()
        df["EMA50"] = df["Close"].ewm(span=50).mean()
        df["EMA200"] = df["Close"].ewm(span=200).mean()

        yesterday = df.iloc[-2]
        day_before = df.iloc[-3]

        entry = (
            yesterday["EMA20"] > yesterday["EMA50"]
            and yesterday["EMA50"] > yesterday["EMA200"]
            and not (
                day_before["EMA20"] > day_before["EMA50"]
                and day_before["EMA50"] > day_before["EMA200"]
            )
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

signals_df = pd.DataFrame(signals, columns=["Ticker", "Neues Signal"])

# ================================
# ✅ FEAR & GREED (ROBUST)
# ================================
fear_greed = "Nicht verfügbar"
try:
    url = "https://api.alternative.me/fng/"
    r = requests.get(url, timeout=10).json()
    fear_greed = r["data"][0]["value"]
except:
    pass

# ================================
# ✅ NASDAQ 100 PERFORMANCE (NUMMERISCH KORREKT)
# ================================
nasdaq_perf = 0.0
try:
    ndx = yf.download("^NDX", period="5d", progress=False)
    ndx_close_today = float(ndx["Close"].iloc[-1])
    ndx_close_yesterday = float(ndx["Close"].iloc[-2])
    nasdaq_perf = (ndx_close_today / ndx_close_yesterday - 1) * 100
except:
    pass

# ================================
# ✅ TELEGRAM FORMATIERUNG
# ================================
entry_list = signals_df[signals_df["Neues Signal"] == "ENTRY"]["Ticker"].tolist()
tp1_list = signals_df[signals_df["Neues Signal"] == "TP1"]["Ticker"].tolist()
tp2_list = signals_df[signals_df["Neues Signal"] == "TP2"]["Ticker"].tolist()
exit_list = signals_df[signals_df["Neues Signal"] == "EXIT"]["Ticker"].tolist()

text = "📊 *TÄGLICHE SIGNALAUSWERTUNG*\n\n"
text += f"🔍 *Heute gescannt:* {checked_count} Aktien\n\n"
text += f"😱 Fear & Greed: {fear_greed}\n"
text += f"📉 Nasdaq-100 gestern: {nasdaq_perf:+.2f} %\n\n"

text += "🚀 *ENTRY Signale:*\n"
text += "\n".join(entry_list) if entry_list else "Keine"
text += "\n\n"

text += "🎯 *TP1:*\n"
text += "\n".join(tp1_list) if tp1_list else "Keine"
text += "\n\n"

text += "🏁 *TP2:*\n"
text += "\n".join(tp2_list) if tp2_list else "Keine"
text += "\n\n"

text += "🛑 *EXIT Signale:*\n"
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

print("====================================")
print("GLOBAL-SCREENER FERTIG")
print("Gescannt:", checked_count)
print("Signale:", len(signals_df))
print("====================================")
