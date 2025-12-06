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
# SIGNAL-LOGIK (wie Backtest + TP1/TP2)
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
    df["SMA120"] = df["Close"].rolling(120).mean()  # aktuell nicht genutzt, schadet aber nicht
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

    last_date = df.index[-1].date()   # Schlusskurs des Vortags (für die Telegram-Meldung)
    signals_today = []

    in_trade = False          # max. 1 Trade pro Ticker
    entry_price = None
    entry_date = None
    tp1_done = False
    tp2_done = False

    # ================================
    # LOOP über die Historie
    # ================================
    for i in range(1, len(df)):

        row  = df.iloc[i]
        prev = df.iloc[i - 1]

        date = row.index if hasattr(row, "index") else row.name
        # row.name ist ein Timestamp (Index)

        date = row.name

        close      = force_float(row["Close"])
        close_prev = force_float(prev["Close"])

        sma20      = force_float(row["SMA20"])
        sma50      = force_float(row["SMA50"])
        sma200     = force_float(row["SMA200"])

        sma20_prev  = force_float(prev["SMA20"])
        sma50_prev  = force_float(prev["SMA50"])
        sma200_prev = force_float(prev["SMA200"])

        # ====================================================
        # ENTRY — nur wenn aktuell kein Trade für diesen Ticker
        # Regel: Close > SMA200 UND SMA20 > SMA50
        # Einstiegssignal am Schlusskurs, Umsetzung am Open des nächsten Tages
        # ====================================================
        entry_condition_now = (
            close > sma200 and
            sma20 > sma50
        )

        entry_condition_prev = (
            close_prev > sma200_prev and
            sma20_prev > sma50_prev
        )

        if not in_trade:
            if entry_condition_now and not entry_condition_prev:
                in_trade    = True
                entry_price = close          # Einstiegskurs (Schlusskurs), Order am nächsten Open
                entry_date  = date
                tp1_done    = False
                tp2_done    = False

                if date.date() == last_date:
                    signals_today.append([ticker, "ENTRY"])

            continue

        # ====================================================
        # EXIT (dynamischer EMA-Stop) – nur nach Entry
        # Stop wechselt je nach Haltedauer, wie im Backtest
        # ====================================================
        days_in_trade = (date - entry_date).days

        if days_in_trade < 60:
            stop = force_float(row["EMA200"])
        elif days_in_trade < 200:
            stop = force_float(row["EMA100"])
        else:
            stop = force_float(row["EMA50"])

        # EXIT-Bedingung (Trade bleibt offen, bis Stop verletzt)
        if close <= stop * 0.97:
            if date.date() == last_date:
                signals_today.append([ticker, "EXIT"])

            # Trade wird geschlossen, nächster ENTRY wieder erlaubt
            in_trade    = False
            entry_price = None
            entry_date  = None
            tp1_done    = False
            tp2_done    = False
            continue

        # ====================================================
        # TP2 = +80% Gewinn seit Entry (nur einmal pro Trade)
        # ====================================================
        if in_trade and (entry_price is not None) and (not tp2_done):
            if close >= entry_price * 1.80:
                tp2_done = True
                if date.date() == last_date:
                    signals_today.append([ticker, "TP2"])

        # ====================================================
        # TP1 = +35% Gewinn seit Entry (nur einmal pro Trade)
        # ====================================================
        if in_trade and (entry_price is not None) and (not tp1_done):
            if close >= entry_price * 1.35:
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

📊 *TP1 (35% Gewinn seit Entry):*
{chr(10).join(tp1_list) if tp1_list else "Keine"}

🚀 *TP2 (80% Gewinn seit Entry):*
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
