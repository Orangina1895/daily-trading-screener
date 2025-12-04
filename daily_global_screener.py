import pandas as pd
import yfinance as yf
import requests
import datetime
import os

# ================================
# ✅ KONFIGURATION
# ================================
START_DEPOT = 30000
RISK_PER_TRADE = 0.005   # 0,5 %
START = "2020-01-01"
END = datetime.date.today().isoformat()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# ================================
# ✅ DEPOT (VIRTUELL)
# ================================
depot_value = START_DEPOT
positions = {}  # Merkt aktive Trades je Ticker

# ================================
# ✅ UNIVERSE: NASDAQ TOP 500 + MDAX + SDAX
# ================================
def load_universe():
    tickers = set()

    # --- NASDAQ TOP 500 ---
    try:
        url = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=500"
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        data = requests.get(url, headers=headers).json()
        rows = data["data"]["table"]["rows"]

        for r in rows:
            if r["symbol"]:
                tickers.add(r["symbol"])

    except:
        tickers |= {
            "AAPL","MSFT","NVDA","AMZN","META","GOOGL","GOOG","TSLA","AVGO",
            "ASML","AMD","NFLX","PLTR","COST","ADBE","ADI"
        }

    # --- MDAX ---
    try:
        mdax = pd.read_html("https://de.wikipedia.org/wiki/MDAX")[0]["Ticker"].dropna()
        tickers |= {f"{t}.DE" for t in mdax}
    except:
        pass

    # --- SDAX ---
    try:
        sdax = pd.read_html("https://de.wikipedia.org/wiki/SDAX")[0]["Ticker"].dropna()
        tickers |= {f"{t}.DE" for t in sdax}
    except:
        pass

    return sorted(list(tickers))

tickers = load_universe()
scanned_count = len(tickers)

# ================================
# ✅ FEAR & GREED INDEX
# ================================
def get_fear_greed():
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        data = requests.get(url).json()
        latest = list(data["fear_and_greed_historical"].values())[-1]
        return f"{latest['score']} ({latest['rating']})"
    except:
        return "Nicht verfügbar"

fear_greed = get_fear_greed()

# ================================
# ✅ NASDAQ-100 PERFORMANCE (GESTERN)
# ================================
try:
    ndx = yf.download("^NDX", period="5d", progress=False)
    ndx_pct = float((ndx["Close"].iloc[-1] - ndx["Close"].iloc[-2]) / ndx["Close"].iloc[-2] * 100)
except:
    ndx_pct = 0.0

# ================================
# ✅ SIGNAL LOGIK
# ================================
signals = []

def in_position(ticker):
    return positions.get(ticker, False)

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
        continue

signals_df = pd.DataFrame(signals, columns=["Ticker", "Signal"])

# ================================
# ✅ TELEGRAM FORMATIERUNG
# ================================
entry_list = signals_df[signals_df["Signal"] == "ENTRY"]["Ticker"].tolist()
tp1_list = signals_df[signals_df["Signal"] == "TP1"]["Ticker"].tolist()
tp2_list = signals_df[signals_df["Signal"] == "TP2"]["Ticker"].tolist()
exit_list = signals_df[signals_df["Signal"] == "EXIT"]["Ticker"].tolist()

text = f"""📡 *DAILY GLOBAL SCREENER*
Ich habe heute ✅ *{scanned_count} Aktien* für dich gescannt

📈 *ENTRY Signale:*
{chr(10).join(entry_list) if entry_list else "Keine"}

📊 *TP1:*
{chr(10).join(tp1_list) if tp1_list else "Keine"}

🚀 *TP2:*
{chr(10).join(tp2_list) if tp2_list else "Keine"}

📉 *EXIT Signale:*
{chr(10).join(exit_list) if exit_list else "Keine"}

😱 *Fear & Greed:* {fear_greed}
📉 *Nasdaq-100 gestern:* {ndx_pct:+.2f} %
"""

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
# ✅ EXCEL EXPORT
# ================================
signals_df.to_excel("daily_signals.xlsx", index=False)

print("====================================")
print("GLOBAL SCREENER FERTIG")
print("Gescannt:", scanned_count)
print("Signale:", len(signals_df))
print("====================================")
