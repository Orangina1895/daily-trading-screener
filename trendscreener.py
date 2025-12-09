# trendscreener.py
#
# Nasdaq-Trend-Screener für GitHub Actions.
# Lädt Kursdaten über yfinance, wendet Momentum-/Trend-/Breakout-Regeln an
# und speichert alle Treffer sowie die letzten 30 Signale als CSV.

import datetime
from typing import List

import pandas as pd
import yfinance as yf


# ============================================
# Parameter
# ============================================
BACKTEST_START = "2018-01-01"  # Startdatum für Historie
TODAY = datetime.date.today().isoformat()

OUTPUT_FULL = "trendscreener_signals_full.csv"
OUTPUT_LATEST30 = "trendscreener_signals_latest30.csv"


def load_universe() -> List[str]:
    """
    Ticker-Universum.
    Hier als Beispiel ein Nasdaq-Schwerpunkt (anpassbar).
    """
    tickers = [
        "AAPL","MSFT","NVDA","AMZN","META","GOOGL","GOOG","TSLA","AVGO","PEP",
        "COST","ADBE","CSCO","NFLX","AMD","INTC","AMGN","QCOM","TXN","SBUX",
        "HON","ADI","AMAT","BKNG","MDLZ","REGN","ISRG","LRCX","MU","GILD",
        "PANW","VRTX","KLAC","ADP","MAR","ABNB","CRWD","MRVL","CHTR","IDXX",
        "CDNS","MELI","KDP","SNPS","FTNT","AZN","ORLY","PCAR","MNST","ADSK",
        "CTAS","PAYX","WDAY","NXPI","ROST","TEAM","ANSS","ODFL","EXC","LULU",
        "AEP","XEL","KHC","CSX","MRNA","BIIB","EA","DLTR","LCID","VRSK",
        "ROKU","ZM","DDOG","ZS","OKTA","MDB","SNOW","HOOD","BE"
    ]
    return tickers


def download_data(tickers: List[str]) -> dict:
    """
    Lädt OHLCV-Daten für alle Ticker als dict: {ticker: DataFrame}.
    """
    data = {}
    for ticker in tickers:
        try:
            df = yf.download(
                ticker,
                start=BACKTEST_START,
                end=TODAY,
                progress=False,
                auto_adjust=True,
            )
            if df.empty:
                continue
            # Nur die nötigen Spalten
            df = df[["Close", "Volume"]].copy()
            df.dropna(inplace=True)
            data[ticker] = df
        except Exception as e:
            print(f"Fehler beim Laden von {ticker}: {e}")
    return data


def compute_signals_for_ticker(ticker: str, df: pd.DataFrame) -> pd.DataFrame:
    """
    Wendet alle Screener-Regeln auf einen Ticker an und gibt alle Signaltage zurück.
    """
    close = df["Close"]
    volume = df["Volume"]

    # Rolling Returns (3/6/12 Monate, Näherung mit Handelstagen)
    ret_3m = close / close.shift(63) - 1.0
    ret_6m = close / close.shift(126) - 1.0
    ret_12m = close / close.shift(252) - 1.0

    # SMAs
    sma50 = close.rolling(50).mean()
    sma150 = close.rolling(150).mean()
    sma200 = close.rolling(200).mean()

    # Steigung der SMAs (heute vs. vor 20 Tagen)
    sma50_shift20 = sma50.shift(20)
    sma200_shift20 = sma200.shift(20)

    # 6M- und 12M-High für Breakouts
    high_6m = close.rolling(126).max()
    high_12m = close.rolling(252).max()

    # Volumen-Filter
    vol_sma50 = volume.rolling(50).mean()

    # Bedingungen
    # Momentum: 3M > 30 %, 6M > 50 %, 12M > 70 %
    momentum_cond = (ret_3m > 0.30) & (ret_6m > 0.50) & (ret_12m > 0.70)

    # Trendfilter: Close > SMA50 > SMA150 > SMA200 + steigende SMAs
    trend_cond = (
        (close > sma50) &
        (sma50 > sma150) &
        (sma150 > sma200) &
        (sma50 > sma50_shift20) &
        (sma200 > sma200_shift20)
    )

    # Breakout + Volumen: neues 6M- oder 12M-Hoch + Volumen >= 2× 50d-Ø
    breakout_cond = (
        (close >= high_6m) | (close >= high_12m)
    ) & (volume >= 2.0 * vol_sma50)

    # Qualitäts-/Liquiditätsfilter
    quality_cond = (
        (close >= 10.0) &
        (vol_sma50 >= 500_000)
    )

    signal_mask = momentum_cond & trend_cond & breakout_cond & quality_cond

    signals = df.loc[signal_mask].copy()
    if signals.empty:
        return pd.DataFrame(columns=[
            "date","ticker","close",
            "ret_3m","ret_6m","ret_12m",
            "sma50","sma150","sma200",
            "volume","vol_sma50"
        ])

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

    # Spalten sortieren
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

    # Nach Datum sortieren (ältestes -> neuestes)
    signals_df.sort_values("date", inplace=True)

    # CSV-Ausgabe (alle Signale)
    signals_df.to_csv(OUTPUT_FULL, index=False)

    # Letzte 30 Signale
    latest30 = signals_df.tail(30).copy()
    latest30.to_csv(OUTPUT_LATEST30, index=False)

    print("Letzte 30 Signale:")
    print(latest30.to_string(index=False))


if __name__ == "__main__":
    run_trendscreener()
