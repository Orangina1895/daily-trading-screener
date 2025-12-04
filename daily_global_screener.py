import yfinance as yf
import pandas as pd
import requests
import os
from datetime import datetime, timedelta

# ================================
# 🔐 TELEGRAM KONFIG
# ================================
TELEGRAM_TOKEN = "DEIN_TELEGRAM_BOT_TOKEN"
CHAT_ID = "DEINE_CHAT_ID"

# ================================
# 📁 STATUS FILE
# ================================
STATUS_FILE = "trade_status.csv"

if os.path.exists(STATUS_FILE):
    status_df = pd.read_csv(STATUS_FILE)
else:
    status_df = pd.DataFrame(columns=["Ticker", "InPosition"])

def in_position(ticker):
    row = status_df[status_df["Ticker"] == ticker]
    if row.empty:
        return False
    return row.iloc[0]["InPosition"] == 1

# ================================
# 📊 TICKER LISTE (NASDAQ TOP 500)
# ================================
print("Lade Nasdaq Top 500 dynamisch...")

nasdaq_url = "https://api.nasdaq.com/api/screener/stocks?exchange=nasdaq&download=true"
headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Referer": "https://www.nasdaq.com"
}

r = requests.get(nasdaq_url, headers=headers)
r.raise_for_status()
data = r.json()

nasdaq_df = pd.DataFrame(data["data"]["rows"])

nasdaq_df = nasdaq_df[["symbol", "marketCap"]].copy()

nasdaq_df["marketCap"] = (
    nasdaq_df["marketCap"]
    .astype(str)
    .str.replace(",", "", regex=False)
    .str.replace("-", "", regex=False)
)

nasdaq_df = nasdaq_df[nasdaq_df["marketCap"].str.strip() != ""]
nasdaq_df["marketCap"] = nasdaq_df["marketCap"].astype(float)

nasdaq_df = nasdaq_df[nasdaq_df["marketCap"] > 0]
nasdaq_df = nasdaq_df.sort_values("marketCap", ascending=False)

tickers = nasdaq_df["symbol"].head(500).tolist()

print("Nasdaq Top 500 geladen:", len(tickers))


# ================================
# 🗓️ DATUM
# ================================
END = datetime.today() - timedelta(days=1)
START = END - timedelta(days=400)

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

        if entry:
            signals.append([TICKER, "ENTRY"])
        elif tp2:
            signals.append([TICKER, "TP2"])
        elif tp1:
            signals.append([TICKER, "TP1"])
        elif exit_sig:
            signals.append([TICKER, "EXIT"])

    except Exception as e:
        print("Fehler bei:", TICKER, e)

signals_df = pd.DataFrame(signals, columns=["Ticker", "Neues Signal"])


        # ================================
        # ✅ TP1 / TP2 (OPTIONAL – NUR BEI AKTIVEM TRADE)
        # ================================
        if in_position(TICKER):

            tp1 = close > df["Close"].rolling(50).max().iloc[-2]
            tp2 = close > df["Close"].rolling(100).max().iloc[-2]

            if tp1:
                signals.append({
                    "Ticker": TICKER,
                    "Neues Signal": "TP1"
                })

            if tp2:
                signals.append({
                    "Ticker": TICKER,
                    "Neues Signal": "TP2"
                })

    except Exception as e:
        print("Fehler bei:", TICKER, e)

# ================================
# ✅ SPEICHERN
# ================================
filename = "daily_signals.xlsx"
signals_df = pd.DataFrame(signals)

signals_df.to_excel(filename, index=False)
status_df.to_csv(STATUS_FILE, index=False)

# ================================
# ✅ TELEGRAM SENDEN (STRUKTURIERT)
# ================================

entry_list = signals_df[signals_df["Neues Signal"] == "ENTRY"]["Ticker"].tolist()
tp1_list   = signals_df[signals_df["Neues Signal"] == "TP1"]["Ticker"].tolist()
tp2_list   = signals_df[signals_df["Neues Signal"] == "TP2"]["Ticker"].tolist()
exit_list  = signals_df[signals_df["Neues Signal"] == "EXIT"]["Ticker"].tolist()

text = "📊 *TRADING-SIGNALE (GESTERN)*\n\n"

if len(entry_list) > 0:
    text += "🟢 *ENTRY Signale:*\n"
    for t in entry_list:
        text += f"- {t}\n"
    text += "\n"

if len(tp1_list) > 0:
    text += "🟡 *TP1:*\n"
    for t in tp1_list:
        text += f"- {t}\n"
    text += "\n"

if len(tp2_list) > 0:
    text += "🟠 *TP2:*\n"
    for t in tp2_list:
        text += f"- {t}\n"
    text += "\n"

if len(exit_list) > 0:
    text += "🔴 *EXIT Signale:*\n"
    for t in exit_list:
        text += f"- {t}\n"
    text += "\n"

if len(signals_df) == 0:
    text = "✅ Keine neuen Signale gestern."

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
print("Datei:", filename)
print("====================================")



