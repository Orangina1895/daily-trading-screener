import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timedelta

# ================================
# ✅ EINSTELLUNGEN
# ================================
START = "1990-01-01"
END = datetime.today().strftime("%Y-%m-%d")

TELEGRAM_TOKEN = "DEIN_TELEGRAM_BOT_TOKEN"
CHAT_ID = "DEINE_CHAT_ID"

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

        tp1 = yesterday["Close"] > 1.1 * day_before["Close"]
        tp2 = yesterday["Close"] > 1.2 * day_before["Close"]

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
