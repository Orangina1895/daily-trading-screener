import os
import json
import datetime as dt
import pandas as pd
import yfinance as yf
import requests

# ================================
# ✅ EINSTELLUNGEN
# ================================
DATA_PERIOD = "300d"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
POSITIONS_FILE = "positions.json"

# ================================
# ✅ FALLBACK TICKER (STABIL)
# ================================
def load_tickers():
    return [
        "NVDA","AAPL","MSFT","GOOG","GOOGL","AMZN","META",
        "TSLA","AVGO","ASML","NFLX","PLTR","COST","AMD","ADBE","ADI"
    ]

# ================================
# ✅ POSITIONEN LADEN / SPEICHERN
# ================================
def load_positions(tickers):
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE, "r") as f:
            positions = json.load(f)
    else:
        positions = {}

    for t in tickers:
        if t not in positions:
            positions[t] = {
                "in_position": False,
                "tp1_hit": False,
                "tp2_hit": False
            }
    return positions


def save_positions(positions):
    with open(POSITIONS_FILE, "w") as f:
        json.dump(positions, f, indent=2)

# ================================
# ✅ FEAR & GREED
# ================================
def get_fear_greed():
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        data = requests.get(url, timeout=10).json()
        return f"{data['fear_and_greed']['score']} – {data['fear_and_greed']['rating']}"
    except:
        return "Nicht verfügbar"

# ================================
# ✅ NASDAQ-100 PERFORMANCE
# ================================
def get_nasdaq100_performance():
    try:
        df = yf.download("^NDX", period="5d", progress=False, auto_adjust=True)

        if len(df) < 2:
            return None

        y = df.iloc[-1]["Close"]
        d = df.iloc[-2]["Close"]

        perf = (y / d - 1) * 100
        return float(round(perf, 2))
    except:
        return None

# ================================
# ✅ TELEGRAM SENDEN
# ================================
def send_telegram(text):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Telegram Daten fehlen.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    requests.post(url, data=payload)

# ================================
# ✅ HAUPTPROGRAMM
# ================================
def main():
    tickers = load_tickers()
    positions = load_positions(tickers)
    signals = []

    print("====================================")
    print("GLOBAL SCREENER START")
    print("Datum:", dt.date.today())
    print("Ticker:", len(tickers))
    print("====================================")

    for TICKER in tickers:
        try:
            df = yf.download(TICKER, period=DATA_PERIOD, progress=False)

            if df.empty or len(df) < 200:
                continue

            df["EMA20"]  = df["Close"].ewm(span=20).mean()
            df["EMA50"]  = df["Close"].ewm(span=50).mean()
            df["EMA200"] = df["Close"].ewm(span=200).mean()
            df = df.dropna()

            yesterday  = df.iloc[-1]
            day_before = df.iloc[-2]

            entry = (
                (yesterday["EMA20"] > yesterday["EMA50"]) and
                (yesterday["EMA50"] > yesterday["EMA200"]) and
                not (
                    (day_before["EMA20"] > day_before["EMA50"]) and
                    (day_before["EMA50"] > day_before["EMA200"])
                )
            )

            exit_sig = (
                (yesterday["Close"] < yesterday["EMA200"]) and
                (day_before["Close"] >= day_before["EMA200"])
            )

            tp1 = yesterday["Close"] >= 1.10 * day_before["Close"]
            tp2 = yesterday["Close"] >= 1.20 * day_before["Close"]

            pos = positions[TICKER]

            if entry and not pos["in_position"]:
                signals.append([TICKER, "ENTRY"])
                pos["in_position"] = True
                pos["tp1_hit"] = False
                pos["tp2_hit"] = False

            elif tp2 and pos["in_position"] and pos["tp1_hit"] and not pos["tp2_hit"]:
                signals.append([TICKER, "TP2"])
                pos["tp2_hit"] = True

            elif tp1 and pos["in_position"] and not pos["tp1_hit"]:
                signals.append([TICKER, "TP1"])
                pos["tp1_hit"] = True

            elif exit_sig and pos["in_position"]:
                signals.append([TICKER, "EXIT"])
                pos["in_position"] = False
                pos["tp1_hit"] = False
                pos["tp2_hit"] = False

            positions[TICKER] = pos

        except Exception as e:
            print("Fehler bei:", TICKER, e)

    save_positions(positions)

    signals_df = pd.DataFrame(signals, columns=["Ticker", "Signal"])

    fear_greed = get_fear_greed()
    nasdaq_perf = get_nasdaq100_performance()

    text = "📊 *TÄGLICHE SIGNALAUSWERTUNG*\n\n"

    def block(name, s):
        lst = signals_df[signals_df["Signal"] == s]["Ticker"].tolist()
        if lst:
            return f"*{name}*\n" + "\n".join(lst) + "\n\n"
        return ""

    text += block("🟢 ENTRY", "ENTRY")
    text += block("🟡 TP1", "TP1")
    text += block("🟠 TP2", "TP2")
    text += block("🔴 EXIT", "EXIT")

    text += "────────────\n"
    text += f"😨 Fear & Greed: {fear_greed}\n"

    if nasdaq_perf is not None:
        text += f"📉 Nasdaq-100 gestern: {nasdaq_perf:+.2f} %\n"

    send_telegram(text)

    print("====================================")
    print("FERTIG | Signale:", len(signals_df))
    print("====================================")

if __name__ == "__main__":
    main()
