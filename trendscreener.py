# trendscreener.py
#
# Nasdaq-Trend-Screener für GitHub Actions.
# Ausgabe als XLSX (Excel), nicht CSV.

import datetime
from typing import List

import pandas as pd
import yfinance as yf


# ============================================
# Parameter
# ============================================
BACKTEST_START = "2018-01-01"
TODAY = datetime.date.today().isoformat()

OUTPUT_FULL = "trendscreener_signals_full.xlsx"
OUTPUT_LATEST30 = "trendscreener_signals_latest30.xlsx"


def load_universe() -> List[str]:
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
    data = {}
    for ticker in tickers:
        try:
            df = yf.download(
                ticker, start=BACKTEST_START, end=TODAY,
                progress=False, auto_adjust=True
            )
            if df.empty:
                continue
            df = df[['Close', 'Volume']].copy()
            df.dropna(inplace=True)
            data[ticker] = df
        except Exception as e:
            print(f"Fehler beim Laden von {ticker}: {e}")
    return data


def compute_signals_for_ticker(ticker: str, df: pd.DataFrame) -> pd.DataFrame:
    close = df["Close"]
    volume = df["Volume"]

    ret_3m = close / close.shift(63) - 1
    ret_6m = close / close.shift(126) - 1
    ret_12m = close / close.shift(252) - 1

    sma50 = close.rolling(50).mean()
    sma150 = close.rolling(150).mean()
    sma200 = close.rolling(200).mean()

    sma50_shift20 = sma50.shift(20)
    sma200_shift20 = sma200.shift(20)

    high_6m = close.rolling(126).max()
    high_12m = close.rolling(252).max()

    vol_sma50 = volume.rolling(50).mean()

    momentum_cond = (ret_3m > 0.30) & (ret_6m > 0.50) & (ret_12m > 0.70)

    trend_cond = (
        (close > sma50) &
        (sma50 > sma150) &
        (sma150 > sma200) &
        (sma50 > sma50_shift20) &
        (sma200 > sma200_shift20)
    )

    breakout_cond = (
        ((close >= high_6m) | (close >= high_12m)) &
        (volume >= 2 * vol_sma50)
    )

    quality_cond = (
        (close >= 10.0) &
        (vol_sma50 >= 500_000)
    )

    signal_mask = momentum_cond & trend_cond & breakout_cond & quality_cond

    signals = df.loc[signal_mask].copy()
    if signals.empty:
        return pd.DataFrame()

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

    # Excel speichern
    signals_df.to_excel(OUTPUT_FULL, index=False)

    latest30 = signals_df.tail(30).copy()
    latest30.to_excel(OUTPUT_LATEST30, index=False)

    print("Letzte 30 Signale:")
    print(latest30.to_string(index=False))


if __name__ == "__main__":
    run_trendscreener()
