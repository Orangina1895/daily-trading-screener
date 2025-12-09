# trendscreener.py
#
# Nasdaq-Trend-Screener für GitHub Actions.
# Ausgabe als XLSX (Excel).

import datetime
from typing import List, Dict

import pandas as pd
import yfinance as yf

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FULL = os.path.join(BASE_DIR, "trendscreener_signals_full.xlsx")
OUTPUT_LATEST30 = os.path.join(BASE_DIR, "trendscreener_signals_latest30.xlsx")


# ============================================
# Parameter
# ============================================
BACKTEST_START = "2018-01-01"
TODAY = datetime.date.today().isoformat()

OUTPUT_FULL = "trendscreener_signals_full.xlsx"
OUTPUT_LATEST30 = "trendscreener_signals_latest30.xlsx"


def load_universe() -> List[str]:
    """
    Universum: Nasdaq-Schwerpunkt inkl. HOOD und BE.
    Ticker, die bei yfinance nicht mehr existieren, werden beim Download übersprungen.
    """
    tickers = [
        "AAPL","MSFT","NVDA","AMZN","META","GOOGL","GOOG","TSLA","AVGO","PEP",
        "COST","ADBE","CSCO","NFLX","AMD","INTC","AMGN","QCOM","TXN","SBUX",
        "HON","ADI","AMAT","BKNG","MDLZ","REGN","ISRG","LRCX","MU","GILD",
        "PANW","VRTX","KLAC","ADP","MAR","ABNB","CRWD","MRVL","CHTR","IDXX",
        "CDNS","MELI","KDP","SNPS","FTNT","AZN","ORLY","PCAR","MNST","ADSK",
        "CTAS","PAYX","WDAY","NXPI","ROST","TEAM","ODFL","EXC","LULU",
        "AEP","XEL","KHC","CSX","MRNA","BIIB","EA","DLTR","LCID","VRSK",
        "ROKU","ZM","DDOG","ZS","OKTA","MDB","SNOW","HOOD","BE"
    ]
    return tickers


def download_data(tickers: List[str]) -> Dict[str, pd.DataFrame]:
    """
    Lädt OHLCV-Daten für alle Ticker.
    Ticker mit Fehlern oder leeren Daten werden übersprungen.
    """
    data: Dict[str, pd.DataFrame] = {}

    for ticker in tickers:
        try:
            df = yf.download(
                ticker,
                start=BACKTEST_START,
                end=TODAY,
                progress=False,
                auto_adjust=True,
            )
            # Wenn yfinance nur Müll liefert -> überspringen
            if df is None or df.empty:
                print(f"Kein gültiger Datensatz für {ticker}, überspringe.")
                continue

            # Manche yfinance-Varianten liefern MultiIndex-Spalten
            if isinstance(df.columns, pd.MultiIndex):
                # typischerweise ('Close', '') etc.
                if ("Close" in df.columns.get_level_values(0) and
                        "Volume" in df.columns.get_level_values(0)):
                    df = df.xs("Close", level=0, axis=1).to_frame("Close").join(
                        df.xs("Volume", level=0, axis=1).to_frame("Volume")
                    )
                else:
                    # notfalls auf einfache Spalten reduzieren
                    df = df.droplevel(1, axis=1)

            if not {"Close", "Volume"}.issubset(df.columns):
                print(f"{ticker}: Close/Volume nicht gefunden, überspringe.")
                continue

            df = df[["Close", "Volume"]].copy()
            df.dropna(inplace=True)

            # zu wenig Historie -> überspringen (z.B. < 260 Handelstage)
            if len(df) < 260:
                print(f"{ticker}: zu wenig Historie ({len(df)} Zeilen), überspringe.")
                continue

            data[ticker] = df

        except Exception as e:
            print(f"Fehler beim Laden von {ticker}: {e}")
            continue

    return data


def compute_signals_for_ticker(ticker: str, df: pd.DataFrame) -> pd.DataFrame:
    """
    Wendet die Screener-Regeln auf einen Ticker an und gibt alle Signaltage zurück.
    Robust gegen NaNs und Index-Mismatches.
    """
    close = df["Close"]
    volume = df["Volume"]

    # Returns (3/6/12 Monate, ca. 63/126/252 Handelstage)
    ret_3m = close / close.shift(63) - 1.0
    ret_6m = close / close.shift(126) - 1.0
    ret_12m = close / close.shift(252) - 1.0

    # SMAs
    sma50 = close.rolling(50).mean()
    sma150 = close.rolling(150).mean()
    sma200 = close.rolling(200).mean()

    sma50_shift20 = sma50.shift(20)
    sma200_shift20 = sma200.shift(20)

    # Highs für Breakouts
    high_6m = close.rolling(126).max()
    high_12m = close.rolling(252).max()

    # Volumen
    vol_sma50 = volume.rolling(50).mean()

    # Alle Bedingungen erst als Series bauen, dann sauber auf df.index ausrichten

    # Momentum
    momentum_cond = (ret_3m > 0.30) & (ret_6m > 0.50) & (ret_12m > 0.70)

    # Trendfilter
    trend_cond = (
        (close > sma50) &
        (sma50 > sma150) &
        (sma150 > sma200) &
        (sma50 > sma50_shift20) &
        (sma200 > sma200_shift20)
    )

    # Breakout + Volumen
    breakout_cond = (
        ((close >= high_6m) | (close >= high_12m)) &
        (volume >= 2.0 * vol_sma50)
    )

    # Qualitäts-/Liquiditätsfilter
    quality_cond = (
        (close >= 10.0) &
        (vol_sma50 >= 500_000)
    )

    # Jetzt alle Bedingungen auf denselben Index bringen und ver-UND-en
    conds = [momentum_cond, trend_cond, breakout_cond, quality_cond]

    signal_mask = pd.Series(True, index=df.index)
    for c in conds:
        # c kann NaNs enthalten -> False
        c = c.reindex(df.index).fillna(False).astype(bool)
        signal_mask &= c

    # Falls aus irgendeinem Grund kein bool Series -> explizit casten
    signal_mask = pd.Series(signal_mask.astype(bool), index=df.index)

    # Filter anwenden
    if not signal_mask.any():
        return pd.DataFrame(
            columns=[
                "date", "ticker", "close",
                "ret_3m", "ret_6m", "ret_12m",
                "sma50", "sma150", "sma200",
                "volume", "vol_sma50",
            ]
        )

    signals = df.loc[signal_mask].copy()

    # Kennzahlen an die Signaltage anhängen
    signals["ret_3m"] = ret_3m.reindex(df.index)[signal_mask]
    signals["ret_6m"] = ret_6m.reindex(df.index)[signal_mask]
    signals["ret_12m"] = ret_12m.reindex(df.index)[signal_mask]
    signals["sma50"] = sma50.reindex(df.index)[signal_mask]
    signals["sma150"] = sma150.reindex(df.index)[signal_mask]
    signals["sma200"] = sma200.reindex(df.index)[signal_mask]
    signals["vol_sma50"] = vol_sma50.reindex(df.index)[signal_mask]

    signals.reset_index(inplace=True)
    signals.rename(columns={"Date": "date"}, inplace=True)
    signals.insert(1, "ticker", ticker)

    # Spaltenreihenfolge fixen
    signals = signals[
        [
            "date",
            "ticker",
            "close",
            "ret_3m",
            "ret_6m",
            "ret_12m",
            "sma50",
            "sma150",
            "sma200",
            "volume",
            "vol_sma50",
        ]
    ]

    return signals


def run_trendscreener():
    tickers = load_universe()
    data = download_data(tickers)

    all_signals = []

    for ticker, df in data.items():
        sig = compute_signals_for_ticker(ticker, df)
        if not sig.empty:
            all_signals.append(sig)

    if not all_signals:
        print("Keine Signale gefunden.")
        return

    signals_df = pd.concat(all_signals, ignore_index=True)
    signals_df.sort_values("date", inplace=True)

    # Vollständige Historie
    signals_df.to_excel(OUTPUT_FULL, index=False)

    # Letzte 30 Treffer
    latest30 = signals_df.tail(30).copy()
    latest30.to_excel(OUTPUT_LATEST30, index=False)

    print("Letzte 30 Signale:")
    print(latest30.to_string(index=False))


if __name__ == "__main__":
    run_trendscreener()
