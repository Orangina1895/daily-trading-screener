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
tickers = pd.read_csv("nasdaq_top_500.csv")["Ticker"].dropna().tolist()

# ================================
# 🗓️ DATUM
# ================================
END = datetime.today() - timedelta(days=1)
START = END - timedelta(days=400)

signals = []

# ================================
# 🔁 SCREENER LOOP
# ================================
for TICKER in tickers:

    try:
        df = yf.download(TICKER, start=START, end=END, progress=False)

        if len(df) < 200:
            continue

        df["EMA50"] = df["Close"].ewm(span=50).mean()
        df["EMA200"] = df["Close"].ewm(span=200).mean()

        last = df.iloc[-1]
        prev = df.iloc[-2]

        close = last["Close"]
        ema50 = last["EMA50"]
        ema200 = last["EMA200"]

        # ================================
        # ✅ ENTRY
        # ================================
        long_signal = close > ema50 and ema50 > ema200 and not in_position(TICKER)

        if long_signal:
            signals.append({
                "Ticker": TICKER,
                "Neues Signal": "ENTRY"
            })

            if TICKER in status_df["Ticker"].values:
                status_df.loc[status_df["Ticker"] == TICKER, "InPosition"] = 1
            else:
                status_df = pd.concat([status_df, pd.DataFrame([{
                    "Ticker": TICKER,
                    "InPosition": 1
                }])])

        # ================================
        # ✅ EXIT (NUR WENN LONG AKTIV)
        # ================================
        exit_signal = close < ema200 and in_position(TICKER)

        if exit_signal:
            signals.append({
                "Ticker": TICKER,
                "Neues Signal": "EXIT"
            })

            status_df.loc[status_df["Ticker"] == TICKER, "InPosition"] = 0

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

