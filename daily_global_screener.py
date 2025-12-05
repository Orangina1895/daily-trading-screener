import pandas as pd
import yfinance as yf
import requests
import datetime
import os

# ================================
# ✅ KONFIGURATION
# ================================
START = "2020-01-01"
END = datetime.date.today().isoformat()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# ================================
# ✅ UNIVERSE LOADER
# ================================
def load_universe():
    tickers = set()

    # ----------------------------
    # ✅ NASDAQ TOP 500
    # ----------------------------
    try:
        print("Lade Nasdaq Top 500...")
        url = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=500"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"
        }
        data = requests.get(url, headers=headers, timeout=20).json()
        rows = data["data"]["table"]["rows"]

        for r in rows:
            if r.get("symbol"):
                tickers.add(r["symbol"])

        print("✅ Nasdaq geladen:", len(rows))

    except Exception as e:
        print("❌ Nasdaq Fehler – Fallback aktiv:", e)
        tickers |= {
            "AAPL","MSFT","NVDA","AMZN","META","GOOGL","GOOG","TSLA","AVGO",
            "ASML","AMD","NFLX","PLTR","COST","ADBE","ADI"
        }

    # ----------------------------
    # ✅ MDAX (CSV)
    # ----------------------------
    try:
        mdax = pd.read_csv("mdax.csv")["Ticker"].dropna()
        tickers |= set(mdax.astype(str))
        print("✅ MDAX geladen:", len(mdax))
    except Exception as e:
        print("❌ MDAX CSV nicht gefunden:", e)

    # ----------------------------
    # ✅ SDAX (CSV)
    # ----------------------------
    try:
        sdax = pd.read_csv("sdax.csv")["Ticker"].dropna()
        tickers |= set(sdax.astype(str))
        print("✅ SDAX geladen:", len(sdax))
    except Exception as e:
        print("❌ SDAX CSV nicht gefunden:", e)

    tickers = sorted(list(tickers))

    print("====================================")
    print("✅ GESAMT-TICKER:", len(tickers))
    print("====================================")

    return tickers


tickers = load_universe()
checked_count = len(tickers)

# ================================
# ✅ NASDAQ-100 PERFORMANCE (GESTERN)
# ================================
try:
    ndx = yf.download("^NDX", period="5d", progress=False)
    ndx_pct = float(
        (ndx["Close"].iloc[-1] - ndx["Close"].iloc[-2])
        / ndx["Close"].iloc[-2] * 100
    )
except:
    ndx_pct = 0.0

# ================================
# ✅ SIGNAL LOGIK
# ================================
signals = []
positions = {}

def in_position(ticker):
    return positions.get(ticker, False)

for TICKER in tickers:
    try:
        df = yf.download(TICKER, start=START, end=END, progress=False)

        if df.empty or len(df) < 250:
            continue

        # NEU: SMA statt EMA für Einstieg
        df["SMA20"] = df["Close"].rolling(20).mean()
        df["SMA50"] = df["Close"].rolling(50).mean()
        df["SMA200"] = df["Close"].rolling(200).mean()

        # Exit-Signale unverändert → weiterhin EMA
        df["EMA200"] = df["Close"].ewm(span=200).mean()

        yesterday = df.iloc[-2]
        day_before = df.iloc[-3]

        # ============================================
        # 🔥 NEUE EINSTIEGSLOGIK
        # Close > SMA200 AND SMA20 > SMA50
        # ============================================
        entry = (
            yesterday["Close"] > yesterday["SMA200"]
            and yesterday["SMA20"] > yesterday["SMA50"]
            and not (
                day_before["Close"] > day_before["SMA200"]
                and day_before["SMA20"] > day_before["SMA50"]
            )
        )

        # ============================================
        # ❗ EXIT SIGNALE UNVERÄNDERT
        # ============================================
        exit_sig = (
            yesterday["Close"] < yesterday["EMA200"]
            and day_before["Close"] >= day_before["EMA200"]
        )

        tp1 = yesterday["Close"] > 1.1 * day_before["Close"]
        tp2 = yesterday["Close"] > 1.2 * day_before["Close"]

        # ============================================
        # SIGNAL HINZUFÜGEN
        # ============================================
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

signals_df = pd.DataFrame(signals, columns=["Ticker", "Signal"])

# ================================
# ✅ TELEGRAM FORMATIERUNG
# ================================
entry_list = signals_df[signals_df["Signal"] == "ENTRY"]["Ticker"].tolist()
tp1_list   = signals_df[signals_df["Signal"] == "TP1"]["Ticker"].tolist()
tp2_list   = signals_df[signals_df["Signal"] == "TP2"]["Ticker"].tolist()
exit_list  = signals_df[signals_df["Signal"] == "EXIT"]["Ticker"].tolist()

text = f"""📡 *DAILY GLOBAL SCREENER*
Ich habe heute ✅ *{checked_count} Aktien* für dich gescannt

📈 *ENTRY Signale:*
{chr(10).join(entry_list) if entry_list else "Keine"}

📊 *TP1:*
{chr(10).join(tp1_list) if tp1_list else "Keine"}

🚀 *TP2:*
{chr(10).join(tp2_list) if tp2_list else "Keine"}

📉 *EXIT Signale:*
{chr(10).join(exit_list) if exit_list else "Keine"}

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
print("Gescannt:", checked_count)
print("Signale:", len(signals_df))
print("====================================")
