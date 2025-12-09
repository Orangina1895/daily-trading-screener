# trendscreener.py
#
# Trend Screener mit:
# 1) Signalen vom Schlusskurs gestern
# 2) vollständiger 12-Monats-Historie aller Signale
# 3) Ausgabe der letzten 30 Signale
# 4) Immer XLSX-Ausgabe
# 5) Performance-Optimierung (Daten ab 01.01.2024)

import datetime
from typing import List, Dict
import os
import pandas as pd
import yfinance as yf

# ============================================
# Pfade (GitHub-sicher)
# ============================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

OUTPUT_HISTORY = os.path.join(BASE_DIR, "signals_history_12m.xlsx")
OUTPUT_TODAY = os.path.join(BASE_DIR, "signals_today.xlsx")
OUTPUT_LATEST30 = os.path.join(BASE_DIR, "signals_latest30.xlsx")

# ============================================
# schneller Startpunkt
# ============================================
BACKTEST_START = "2024-01-01"

TODAY = datetime.date.today()
YESTERDAY = TODAY - datetime.timedelta(days=1)
HISTORY_12M = TODAY - datetime.timedelta(days=365)


# ============================================
# Universum (frei anpassbar)
# ============================================
def load_universe() -> List[str]:
    return [
        "AAPL","MSFT","NVDA","AMZN","META","GOOGL","GOOG","TSLA","AVGO","PEP",
        "COST","ADBE","CSCO","NFLX","AMD","INTC","AMGN","QCOM","TXN","SBUX",
        "HON","ADI","AMAT","BKNG","MDLZ","REGN","ISRG","LRCX","MU","GILD",
        "PANW","VRTX","KLAC","ADP","MAR","ABNB","CRWD","MRVL","CHTR","IDXX",
        "CDNS","MELI","KDP","SNPS","FTNT","AZN","ORLY","PCAR","MNST","ADSK",
        "CTAS","PAYX","WDAY","NXPI","ROST","TEAM","ODFL","EXC","LULU","AEP",
        "XEL","KHC","CSX","MRNA","BIIB","EA","DLTR","LCID","VRSK","ROKU",
        "ZM","DDOG","ZS","OKTA","MDB","SNOW","HOOD","BE"
    ]


# ============================================
# Daten laden
# ============================================
def download_data(tickers: List[str]) -> Dict[str, pd.DataFrame]:
    data = {}
    for t in tickers:
        try:
            df = yf.download(
                t,
                start=BACKTEST_START,
                end=TODAY + datetime.timedelta(days=1),
                auto_adjust=True,
                progress=False,
            )
            if df.empty:
                continue

            df = df[["Close", "Volume"]].copy()
            df.dropna(inplace=True)
            data[t] = df

        except Exception as e:
            print(f"Fehler bei {t}: {e}")
            continue

    return data


# ============================================
# Signallogik (Trendstarter)
# ============================================
def ensure_series(x, df):
    if isinstance(x, pd.DataFrame):
        if x.shape[1] != 1:
            raise ValueError("Mehrspaltige Maske entdeckt.")
        x = x.iloc[:, 0]
    return x.reindex(df.index).fillna(False).astype(bool)


def compute_signals(ticker: str, df: pd.DataFrame) -> pd.DataFrame:

    close = df["Close"]
    volume = df["Volume"]

    sma50 = close.rolling(50).mean()
    sma150 = close.rolling(150).mean()
    sma200 = close.rolling(200).mean()

    sma50_shift20 = sma50.shift(20)
    sma200_shift20 = sma200.shift(20)

    ret_3m = close.pct_change(63)
    ret_6m = close.pct_change(126)
    ret_12m = close.pct_change(252)

    high_6m = close.rolling(126).max()
    vol_sma50 = volume.rolling(50).mean()

    momentum_cond = (
        (ret_3m > 0.15) &
        (ret_6m > 0.30) &
        (ret_12m > 0.40)
    )

    trend_cond = (
        (close > sma50) &
        (sma50 > sma150) &
        (sma150 > sma200) &
        (sma50 > sma50_shift20) &
        (sma200 > sma200_shift20)
    )

    breakout_cond = (
        (close >= 0.98 * high_6m) &
        (volume >= 1.5 * vol_sma50)
    )

    quality_cond = (
        (close >= 3.0) &
        (vol_sma50 >= 100_000)
    )

    # === neue sichere Maskenverarbeitung ===
    momentum_cond  = ensure_series(momentum_cond, df)
    trend_cond     = ensure_series(trend_cond, df)
    breakout_cond  = ensure_series(breakout_cond, df)
    quality_cond   = ensure_series(quality_cond, df)

    signal_mask = momentum_cond & trend_cond & breakout_cond & quality_cond

    if not signal_mask.any():
        return pd.DataFrame()



# ============================================
# Hauptfunktion
# ============================================
def run_trendscreener():

    tickers = load_universe()
    data = download_data(tickers)

    all_signals = []

    for ticker, df in data.items():
        sig = compute_signals(ticker, df)
        if not sig.empty:
            all_signals.append(sig)

    # Wenn es Signale gab
    if all_signals:
        history_df = pd.concat(all_signals, ignore_index=True)
    else:
        history_df = pd.DataFrame(columns=["date", "ticker", "close"])

    # Nur 12M
    history_12m = history_df[history_df["date"] >= pd.Timestamp(HISTORY_12M)]

    # Neue Signale von gestern
    signals_yesterday = history_df[history_df["date"] == pd.Timestamp(YESTERDAY)]

    # Letzten 30 Signale
    latest30 = history_12m.sort_values("date").tail(30)

    # XLSX speichern
    history_12m.to_excel(OUTPUT_HISTORY, index=False)
    signals_yesterday.to_excel(OUTPUT_TODAY, index=False)
    latest30.to_excel(OUTPUT_LATEST30, index=False)

    # Log-Ausgabe
    print("\n===== LETZTE 30 SIGNALE =====")
    print(latest30[["date","ticker","close"]].to_string(index=False))

    print("\n===== SIGNAL VON GESTERN =====")
    if signals_yesterday.empty:
        print("Keine neuen Signale gestern.")
    else:
        print(signals_yesterday[["date","ticker","close"]].to_string(index=False))

    print("\nDateien erstellt:")
    print(f" → {OUTPUT_HISTORY}")
    print(f" → {OUTPUT_TODAY}")
    print(f" → {OUTPUT_LATEST30}")


if __name__ == "__main__":
    run_trendscreener()
