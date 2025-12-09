# trendscreener.py
#
# Finaler Trend-Screener für GitHub Actions
# - Ausgabe IMMER als XLSX
# - geeignet für Smallcap-Trendstarter
# - zeigt die letzten 30 Signale mit Datum
# - speichert garantiert im Repo-Ordner

import datetime
from typing import List, Dict
import os
import pandas as pd
import yfinance as yf


# ============================================
# Pfade (100 % GitHub-sicher)
# ============================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FULL = os.path.join(BASE_DIR, "trendscreener_signals_full.xlsx")
OUTPUT_LATEST30 = os.path.join(BASE_DIR, "trendscreener_signals_latest30.xlsx")

BACKTEST_START = "2016-01-01"
TODAY = datetime.date.today().isoformat()


# ============================================
# Universum (Nasdaq + spannende Trendstarter)
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
# Datenabruf
# ============================================
def download_data(tickers: List[str]) -> Dict[str, pd.DataFrame]:
    data = {}
    for ticker in tickers:
        try:
            df = yf.download(
                ticker,
                start=BACKTEST_START,
                end=TODAY,
                auto_adjust=True,
                progress=False,
            )

            if df is None or df.empty:
                print(f"Überspringe {ticker}: Keine Daten.")
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df = df['Close'].to_frame().join(df['Volume'].to_frame())
                df.columns = ["Close", "Volume"]

            if not {"Close", "Volume"}.issubset(df.columns):
                print(f"Überspringe {ticker}: Close/Volume fehlen.")
                continue

            df = df[["Close", "Volume"]].copy()
            df.dropna(inplace=True)

            if len(df) < 260:
                print(f"Überspringe {ticker}: zu wenig Historie.")
                continue

            data[ticker] = df

        except Exception as e:
            print(f"Fehler bei {ticker}: {e}")
    return data


# ============================================
# Signal-Logik
# ============================================
def compute_signals_for_ticker(ticker: str, df: pd.DataFrame) -> pd.DataFrame:

    close = df["Close"]
    volume = df["Volume"]

    # Returns
    ret_3m = close / close.shift(63) - 1
    ret_6m = close / close.shift(126) - 1
    ret_12m = close / close.shift(252) - 1

    # SMAs
    sma50 = close.rolling(50).mean()
    sma150 = close.rolling(150).mean()
    sma200 = close.rolling(200).mean()
    sma50_shift20 = sma50.shift(20)
    sma200_shift20 = sma200.shift(20)

    # Highs
    high_6m = close.rolling(126).max()

    # Volumen
    vol_sma50 = volume.rolling(50).mean()

    # Momentum (Smallcap-tauglich)
    momentum_cond = (
        (ret_3m > 0.15) &      # früher!
        (ret_6m > 0.30) &
        (ret_12m > 0.40)
    )

    # Trendfilter (leichter, um Smallcaps früh zu erwischen)
    trend_cond = (
        (close > sma50) &
        (sma50 > sma150) &
        (sma150 > sma200) &
        (sma50 > sma50_shift20) &
        (sma200 > sma200_shift20)
    )

    # Früher Breakout
    breakout_cond = (
        (close >= high_6m * 0.98) &                # 2 % unter Hoch → Trendstart
        (volume >= 1.5 * vol_sma50)                # deutlicher Volumenschub
    )

    # Smallcap-Qualität
    quality_cond = (
        (close >= 3.0) &                           # auch $3 – $10 Stocks
        (vol_sma50 >= 100_000)                     # nicht illiquide
    )

    conds = [momentum_cond, trend_cond, breakout_cond, quality_cond]
    signal_mask = pd.Series(True, index=df.index)

    for c in conds:
        c = c.reindex(df.index).fillna(False).astype(bool)
        signal_mask &= c

    if not signal_mask.any():
        return pd.DataFrame()

    signals = df.loc[signal_mask].copy()

    signals["ret_3m"] = ret_3m[signal_mask]
    signals["ret_6m"] = ret_6m[signal_mask]
    signals["ret_12m"] = ret_12m[signal_mask]
    signals["sma50"] = sma50[signal_mask]
    signals["sma150"] = sma150[signal_mask]
    signals["sma200"] = sma200[signal_mask]
    signals["vol_sma50"] = vol_sma50[signal_mask]

    signals.reset_index(inplace=True)
    signals.rename(columns={"Date": "date"}, inplace=True)
    signals.insert(1, "ticker", ticker)

    return signals


# ============================================
# Screener ausführen
# ============================================
def run_trendscreener():
    tickers = load_universe()
    data = download_data(tickers)

    all_signals = []

    for ticker, df in data.items():
        sig = compute_signals_for_ticker(ticker, df)
        if not sig.empty:
            all_signals.append(sig)

    # Immer DataFrame erzeugen
    if all_signals:
        signals_df = pd.concat(all_signals, ignore_index=True)
        signals_df.sort_values("date", inplace=True)
    else:
        print("WARNUNG: Keine Signale gefunden.")
        signals_df = pd.DataFrame(
            columns=[
                "date","ticker","close",
                "ret_3m","ret_6m","ret_12m",
                "sma50","sma150","sma200",
                "volume","vol_sma50"
            ]
        )

    # Speichern
    signals_df.to_excel(OUTPUT_FULL, index=False)
    latest30 = signals_df.tail(30).copy()
    latest30.to_excel(OUTPUT_LATEST30, index=False)

    # Konsole ausgeben
    print("\nLETZTE 30 SIGNALE:")
    print(latest30.to_string(index=False))

    print("\nDateien erstellt in:", BASE_DIR)
    print("->", OUTPUT_FULL)
    print("->", OUTPUT_LATEST30)


if __name__ == "__main__":
    run_trendscreener()
