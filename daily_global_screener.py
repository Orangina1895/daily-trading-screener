import yfinance as yf
import pandas as pd
import requests
from datetime import datetime

# ================================
# 🔐 TELEGRAM DATEN
# ================================
import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
# ================================
# PARAMETER
# ================================
START = "1990-01-01"
LEVERAGE = 3

# ================================
# ✅ NASDAQ COMPOSITE AUTOMATISCH LADEN
# ================================
print("Lade Nasdaq Composite Liste...")

import requests
import io

print("Lade Nasdaq-Aktien über Nasdaq-API und filtere Top 500 nach MarketCap...")

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

# ✅ Nur Spalten mit Symbol + MarketCap
nasdaq_df = nasdaq_df[["symbol", "marketCap"]]

# ✅ ALLE leeren, None, "-" etc. entfernen
nasdaq_df["marketCap"] = (
    nasdaq_df["marketCap"]
    .astype(str)
    .str.replace(",", "", regex=False)
    .str.replace("-", "", regex=False)
)

nasdaq_df = nasdaq_df[nasdaq_df["marketCap"].str.strip() != ""]

# ✅ Jetzt erst sicher zu float konvertieren
nasdaq_df["marketCap"] = nasdaq_df["marketCap"].astype(float)

# ✅ Nur positive MarketCaps
nasdaq_df = nasdaq_df[nasdaq_df["marketCap"] > 0]

# ✅ Nach Größe sortieren
nasdaq_df = nasdaq_df.sort_values("marketCap", ascending=False)

# ✅ Top 500
NASDAQ_TOP500 = nasdaq_df["symbol"].head(500).tolist()

print("Anzahl Nasdaq Top-500-Aktien:", len(NASDAQ_TOP500))



# ================================
# ✅ MDAX & SDAX FEST
# ================================
MDAX = [
"AIXA.DE","EVK.DE","LEG.DE","RHM.DE","SOW.DE","SZU.DE","PUM.DE",
"JEN.DE","KRN.DE","WCH.DE","HFG.DE","MTX.DE","G1A.DE"
]

SDAX = [
"S92.DE","TTK.DE","GFT.DE","O2D.DE","DEQ.DE","SAX.DE","LXS.DE",
"DER.DE","NOR.DE","YOU.DE"
]

UNIVERSE = NASDAQ_TOP500 + MDAX + SDAX


signals = []

# ================================
# ✅ SCREENER
# ================================
for TICKER in UNIVERSE:

    try:
        df = yf.download(TICKER, start=START, progress=False)
    except:
        continue

    if df.empty or len(df) < 250:
        continue

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[["Close"]].dropna()

    df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()
    df["EMA100"] = df["Close"].ewm(span=100, adjust=False).mean()
    df["SMA20"]  = df["Close"].rolling(20).mean()
    df["SMA50"]  = df["Close"].rolling(50).mean()
    df["SMA120"] = df["Close"].rolling(120).mean()
    df["SMA200"] = df["Close"].rolling(200).mean()

    if len(df) < 210:
        continue

    y = df.iloc[-2]
    p = df.iloc[-3]

    # ✅ ENTRY (nur neu!)
    entry_y = y["SMA20"] > y["SMA50"] > y["SMA120"] > y["SMA200"] and y["Close"] > y["EMA200"]
    entry_p = p["SMA20"] > p["SMA50"] > p["SMA120"] > p["SMA200"] and p["Close"] > p["EMA200"]

    if entry_y and not entry_p:
        signals.append([TICKER, "ENTRY"])
        continue

    # ✅ TP / EXIT (nur neu)
    entry_price = df["Close"].iloc[-60]

    perf_y = ((df["Close"].iloc[-2] / entry_price) - 1) * 100 * LEVERAGE
    perf_p = ((df["Close"].iloc[-3] / entry_price) - 1) * 100 * LEVERAGE

    if perf_y >= 1000 and perf_p < 1000:
        signals.append([TICKER, "TP1_1000%"])
        continue

    if perf_y >= 2000 and perf_p < 2000:
        signals.append([TICKER, "TP2_2000%"])
        continue

    exit_y = y["Close"] < y["EMA100"] * 0.97
    exit_p = p["Close"] < p["EMA100"] * 0.97

    if exit_y and not exit_p:
        signals.append([TICKER, "EXIT"])
        continue

# ================================
# ✅ EXCEL
# ================================
signals_df = pd.DataFrame(signals, columns=["Ticker", "Neues Signal"])
date_str = datetime.now().strftime("%Y-%m-%d")
filename = f"daily_signals_{date_str}.xlsx"
signals_df.to_excel(filename, index=False)

# ================================
# ✅ TELEGRAM
# ================================
if len(signals_df) > 0:
    text = "📈 *NEUE TRADING-SIGNALE (GESTERN)*\n\n"
    for _, row in signals_df.iterrows():
        text += f"{row['Ticker']} → {row['Neues Signal']}\n"
else:
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




