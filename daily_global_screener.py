import pandas as pd
import yfinance as yf
import requests
import datetime
import os

# ================================
# KONFIGURATION
# ================================
HISTORY_START = "2023-01-01"
BACKTEST_START = datetime.datetime(2025, 1, 1)
END = datetime.date.today().isoformat()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")


# ================================
# NASDAQ-100 Universe (ALLE 100 TICKER)
# ================================
def load_universe():

    NASDAQ100 = [
        "AAPL","MSFT","NVDA","AMZN","META","GOOGL","GOOG","TSLA","AVGO","PEP",
        "COST","ADBE","CSCO","NFLX","AMD","INTC","AMGN","QCOM","TXN","SBUX",
        "HON","ADI","AMAT","BKNG","MDLZ","REGN","ISRG","LRCX","MU","GILD",
        "PANW","VRTX","KLAC","PYPL","ADP","MAR","ABNB","CRWD","MRVL","CHTR",
        "IDXX","CDNS","MELI","KDP","SNPS","FTNT","AZN","ORLY","PCAR","MNST",
        "ADSK","CTAS","PAYX","WDAY","NXPI","ROST","TEAM","ANSS","ODFL","EXC",
        "LULU","AEP","XEL","KHC","CSX","MRNA","BIIB","EA","DLTR","LCID",
        "PDD","JD","BIDU","ZM","DOCU","OKTA","ZS","SPLK","VRSN","EBAY",
        "ILMN","MNDT","FISV","CTSH","ALGN","FAST","DXCM","CPRT","MTCH","SWKS",
        "TTD","SGEN","QRVO","CRUS","JBHT","AVLR","TTWO","VRSK","NTES","BMRN"
    ]

    print("====================================")
    print("📈 NASDAQ-100 geladen:", len(NASDAQ100))
    print("====================================")

    return sorted(NASDAQ100)


tickers = load_universe()
checked_count = len(tickers)


# ================================
# NASDAQ-100 PERFORMANCE GESTERN
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
# Hilfsfunktion
# ================================
def force_float(x):
    try:
        if isinstance(x, pd.Series):
            return float(x.iloc[0])
        return float(x)
    except:
        return float("nan")


# ================================
# SIGNAL-LOGIK (wie Backtest)
# ================================
def process_ticker_daily(ticker):
    try:
        df = yf.download(ticker, start=HISTORY_START, end=END, progress=False)
    except:
        return []

    if df.empty:
        return []

    # Indikatoren berechnen
    df["SMA20"]  = df["Close"].rolling(20).mean()
    df["SMA50"]  = df["Close"].rolling(50).mean()
    df["SMA120"] = df["Close"].rolling(120).mean()
    df["SMA200"] = df["Close"].rolling(200).mean()

    df["EMA200"] = df["Close"].ewm(span=200).mean()
    df["EMA100"] = df["Close"].ewm(span=100).mean()
    df["EMA50"]  = df["Close"].ewm(span=50).mean()

    df = df.dropna().copy()
    if df.empty:
        return []

    df = df[df.index >= BACKTEST_START]
    if df.empty:
        return []

    last_date = df.index[-1].date()
    signals_today = []

    in_trade = False
    entry_date = None
    tp1_done = False
    tp2_done = False

    for i in range(1, len(df)):

        row  = df.iloc[i]
        prev = df.iloc[i - 1]

        date = row.name

        c_close = force_float(row["Close"])
        p_close = force_float(prev["Close"])

        sma20   = force_float(row["SMA20"])
        sma50   = force_float(row["SMA50"])
        sma200  = force_float(row["SMA200"])

        prev_sma20  = force_float(prev["SMA20"])
        prev_sma50  = force_float(prev["SMA50"])
        prev_sma200 = force_float(prev["SMA200"])

        # ---------------------------------
        # ENTRY Regel
        entry_condition = (
            c_close > sma200 and
            sma20 > sma50
        )

        prev_entry_condition = (
            p_close > prev_sma200 and
            prev_sma20 > prev_sma50
        )

        if not in_trade:
            if entry_condition and not prev_entry_condition:

                in_trade   = True
                entry_date = date
                tp1_done   = False
                tp2_done   = False

                if date.date() == last_date:
                    signals_today.append([ticker, "ENTRY"])
            continue

        # ---------------------------------
        # DYNAMISCHER EXIT
        days = (date - entry_date).days

        if days < 60:
            stop = force_float(row["EMA200"])
        elif days < 200:
            stop = force_float(row["EMA100"])
        else:
            stop = force_float(row["EMA50"])

        # EXIT (höchste Priorität)
        if c_close <= stop * 0.97:
            if date.date() == last_date:
                signals_today.append([ticker, "EXIT"])

            in_trade = False
            entry_date = None
            continue

        # ---------------------------------
        # TP2 → +20% ggü. Vortag (nur einmal)
        if (not tp2_done) and (c_close >= p_close * 1.20):
            tp2_done = True
            if date.date() == last_date:
                signals_today.append([ticker, "TP2"])

        # ---------------------------------
        # TP1 → +10% ggü. Vortag (nur einmal)
        elif (not tp1_done) and (c_close >= p_close * 1.10):
            tp1_done = True
            if date.date() == last_date:
                signals_today.append([ticker, "TP1"])

    return signals_today


# ================================
# SCAN AUSFÜHREN
# ================================
all_signals = []

for T in tickers:
    print("Berechne:", T)
    try:
        s = process_ticker_daily(T)
        all_signals.extend(s)
    except Exception as e:
        print("Fehler bei:", T, e)

signals_df = pd.DataFrame(all_signals, columns=["Ticker", "Signal"])


# ================================
# TELEGRAM FORMAT
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
# TELEGRAM SENDEN
# ================================
requests.post(
    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
    data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"},
)

# ================================
# EXCEL EXPORT
# ================================
signals_df.to_excel("daily_signals.xlsx", index=False)

print("\n====================================")
print("GLOBAL SCREENER FERTIG")
print("Gescannt:", checked_count)
print("Signale:", len(signals_df))
print("====================================\n")
