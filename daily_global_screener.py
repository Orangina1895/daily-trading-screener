import yfinance as yf
import pandas as pd
import requests
import datetime
import os

# ================================
# ✅ KONFIG
# ================================
START = "2020-01-01"
END = datetime.datetime.today().strftime("%Y-%m-%d")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

POSITIONS_FILE = "positions.csv"

# ================================
# ✅ FEAR & GREED
# ================================
def get_fear_greed():
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        r = requests.get(url, timeout=10)
        data = r.json()
        return str(int(data["fear_and_greed"]["score"]))
    except:
        return "API blockiert (CNN)"

# ================================
# ✅ NASDAQ-100 PERFORMANCE
# ================================
def get_nasdaq_perf():
    try:
        df = yf.download("^NDX", period="5d", progress=False)
        if len(df) < 2:
            return 0.0
        prev = df.iloc[-2]["Close"]
        last = df.iloc[-1]["Close"]
        return ((last - prev) / prev) * 100
    except:
        return 0.0

# ================================
# ✅ TICKER LADEN (CSV)
# ================================
def load_tickers():
    try:
        nasdaq = pd.read_csv("nasdaq500.csv")["Ticker"].dropna().tolist()
        mdax = pd.read_csv("mdax.csv")["Ticker"].dropna().tolist()
        sdax = pd.read_csv("sdax.csv")["Ticker"].dropna().tolist()
        return list(set(nasdaq + mdax + sdax))
    except:
        print("⚠️ CSV-Dateien fehlen – Fallback aktiv")
        return ["NVDA", "AAPL", "MSFT", "AMZN", "META", "TSLA", "PLTR", "AMD", "ADI", "ASML"]

# ================================
# ✅ POSITIONSVERWALTUNG
# ================================
def load_positions():
    try:
        df = pd.read_csv(POSITIONS_FILE)
        return dict(zip(df["Ticker"], df["InPosition"]))
    except:
        return {}

def save_positions(positions):
    df = pd.DataFrame(list(positions.items()), columns=["Ticker", "InPosition"])
    df.to_csv(POSITIONS_FILE, index=False)

def in_position(ticker):
    return positions.get(ticker, False)

# ================================
# ✅ TELEGRAM
# ================================
def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    requests.post(url, data=payload)

# ================================
# ✅ HAUPTPROGRAMM
# ================================
tickers = load_tickers()
positions = load_positions()

signals = []
scanned = 0

print("====================================")
print("GLOBAL-SCREENER START")
print("Datum:", END)
print("Anzahl Ticker:", len(tickers))
print("====================================")

for TICKER in tickers:
    scanned += 1
    try:
        df = yf.download(TICKER, start=START, end=END, progress=False)

        if df.empty or len(df) < 250:
            continue

        df["EMA20"] = df["Close"].ewm(span=20).mean()
        df["EMA50"] = df["Close"].ewm(span=50).mean()
        df["EMA200"] = df["Close"].ewm(span=200).mean()

        yesterday = df.iloc[-2]
        prev = df.iloc[-3]

        entry = (
            yesterday["EMA20"] > yesterday["EMA50"] > yesterday["EMA200"]
            and not (prev["EMA20"] > prev["EMA50"] > prev["EMA200"])
        )

        exit_sig = (
            yesterday["Close"] < yesterday["EMA200"]
            and prev["Close"] >= prev["EMA200"]
        )

        tp1 = yesterday["Close"] >= 1.10 * prev["Close"]
        tp2 = yesterday["Close"] >= 1.20 * prev["Close"]

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

# ================================
# ✅ SIGNALAUSWERTUNG
# ================================
signals_df = pd.DataFrame(signals, columns=["Ticker", "Signal"])

entry_list = signals_df[signals_df["Signal"] == "ENTRY"]["Ticker"].tolist()
tp1_list = signals_df[signals_df["Signal"] == "TP1"]["Ticker"].tolist()
tp2_list = signals_df[signals_df["Signal"] == "TP2"]["Ticker"].tolist()
exit_list = signals_df[signals_df["Signal"] == "EXIT"]["Ticker"].tolist()

save_positions(positions)

# ================================
# ✅ ZUSATZDATEN
# ================================
fear_greed = get_fear_greed()
nasdaq_perf = get_nasdaq_perf()

# ================================
# ✅ TELEGRAM TEXT
# ================================
text = "📡 DAILY GLOBAL SCREENER\n"
text += f"Ich habe heute ✅ {scanned} Aktien für dich gescannt\n\n"

text += "📈 ENTRY Signale:\n" + ("\n".join(entry_list) if entry_list else "Keine") + "\n\n"
text += "📊 TP1:\n" + ("\n".join(tp1_list) if tp1_list else "Keine") + "\n\n"
text += "🚀 TP2:\n" + ("\n".join(tp2_list) if tp2_list else "Keine") + "\n\n"
text += "📉 EXIT Signale:\n" + ("\n".join(exit_list) if exit_list else "Keine") + "\n\n"

text += f"😱 Fear & Greed: {fear_greed}\n"
text += f"📉 Nasdaq-100 gestern: {nasdaq_perf:+.2f} %"

send_telegram(text)

print("✅ Telegram gesendet")
