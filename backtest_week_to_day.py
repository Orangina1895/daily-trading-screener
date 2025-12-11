#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

# ==========================================================
# 1. TICKER-UNIVERSUM (bereinigt)
# ==========================================================

TICKERS = [
    "AAPL","ADBE","ADI","ADP","ADSK","ALGN","ALXN","AMAT","AMGN","AMD","AMZN",
    "ANSS","ASML","ATVI","AVGO","BIDU","BIIB","BMRN","BKNG","CDNS","CDW","CERN",
    "CHKP","CHTR","CMCSA","CPRT","COST","CSCO","CSGP","CSX","CTAS","CTSH","CTXS",
    "DLTR","DXCM","EA","EBAY","EXC","EXPE","FAST","FB","FISV","FOX","FOXA",
    "GILD","GOOG","GOOGL","IDXX","ILMN","INCY","INTC","INTU","ISRG","JD","KHC",
    "KLAC","LBTYA","LBTYK","LRCX","LULU","MAR","MCHP","MDLZ","MELI","META",
    "MNST","MRVL","MU","NFLX","NTAP","NTES","NVDA","NXPI","ORLY","PAYX","PCAR",
    "PEP","PYPL","QCOM","REGN","ROST","SBUX","SIRI","SGEN","SNPS","SPLK","TCOM",
    "TMUS","TSLA","TTWO","TXN","ULTA","VRSK","VRSN","VRTX","XLNX"
]

print(f"Universum geladen: {len(TICKERS)} Aktien")

# ==========================================================
# 2. ZEITRAUM
# ==========================================================

HISTORY_START = pd.Timestamp("2018-01-01")
BACKTEST_START = pd.Timestamp("2018-01-01")
EXIT_DATE = pd.Timestamp.today().normalize()

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_FILE = f"week_to_day_backtest_{timestamp}.xlsx"
MISSING_FILE = f"missing_tickers_{timestamp}.xlsx"

# ==========================================================
# 3. INDICATORS (Weekly)
# ==========================================================

def add_indicators(df):
    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)

    df["ema50"] = close.ewm(span=50).mean()
    df["ema100"] = close.ewm(span=100).mean()
    df["ema200"] = close.ewm(span=200).mean()

    df["sma20"] = close.rolling(20).mean()
    df["sma50"] = close.rolling(50).mean()
    df["sma200"] = close.rolling(200).mean()

    # ATR
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1/14).mean()

    # ADX
    up = high.diff()
    down = -low.diff()

    plus_dm = np.where((up > down) & (up > 0), up, 0)
    minus_dm = np.where((down > up) & (down > 0), down, 0)

    atr = df["atr"]
    plus = pd.Series(plus_dm, index=df.index).ewm(alpha=1/14).mean()
    minus = pd.Series(minus_dm, index=df.index).ewm(alpha=1/14).mean()

    plus_di = 100 * (plus / atr)
    minus_di = 100 * (minus / atr)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)

    df["adx"] = dx.ewm(alpha=1/14).mean()
    df["slope"] = df["sma200"] - df["sma200"].shift(10)

    return df


# ==========================================================
# 4. STRATEGIE (Weekly Entry, Daily Exit)
# ==========================================================

def run_strategy(df, ticker):

    rows = []
    position = False
    entry_price = 0.0
    entry_date = None
    cooldown = -1
    daily_df = None

    close = df["Close"].values

    for i in range(len(df)):
        date = df.index[i]

        if date < BACKTEST_START:
            continue

        # ==========================================================
        # EXIT (Daily)
        # ==========================================================
        if position:

            if daily_df is None:
                daily_df = yf.download(
                    ticker,
                    start=entry_date,
                    end=EXIT_DATE,
                    interval="1d",
                    progress=False
                )

                daily_df["ema50"] = daily_df["Close"].ewm(span=50).mean()
                daily_df["ema100"] = daily_df["Close"].ewm(span=100).mean()
                daily_df["ema200"] = daily_df["Close"].ewm(span=200).mean()

                daily_idx_entry = daily_df.index.get_loc(entry_date, method="bfill")

            if date <= daily_df.index[-1]:
                j = daily_df.index.get_indexer([date], method="ffill")[0]
                days_open = j - daily_idx_entry

                if days_open <= 50:
                    crit_ema = daily_df["ema200"].iloc[j]
                elif days_open <= 100:
                    crit_ema = daily_df["ema100"].iloc[j]
                else:
                    crit_ema = daily_df["ema50"].iloc[j]

                if daily_df["Close"].iloc[j] < crit_ema:

                    exit_price = float(close[i])
                    ret_pct = (exit_price / entry_price - 1) * 100

                    rows.append([ticker, "EXIT", date, exit_price, ret_pct])

                    position = False
                    entry_price = 0.0
                    entry_date = None
                    cooldown = i + 15
                    daily_df = None
                    continue

        # ==========================================================
        # ENTRY (Weekly)
        # ==========================================================
        if not position and i > cooldown:

            if (
                close[i] > df["sma200"].iloc[i] and
                df["sma20"].iloc[i] > df["sma50"].iloc[i] and
                df["adx"].iloc[i] > 20 and
                df["slope"].iloc[i] > 0 and
                abs(df["ema50"].iloc[i] - df["ema200"].iloc[i]) / close[i] > 0.01 and
                df["atr"].iloc[i] / close[i] > 0.005
            ):
                position = True
                entry_price = float(close[i])
                entry_date = date
                rows.append([ticker, "ENTRY", entry_date, entry_price, ""])
                daily_df = None

    # ==========================================================
    # FORCED EXIT
    # ==========================================================
    if position:
        exit_price = float(close[-1])
        ret_pct = (exit_price / entry_price - 1) * 100
        rows.append([ticker, "EXIT", EXIT_DATE, exit_price, ret_pct])

    return rows


# ==========================================================
# 5. MAIN
# ==========================================================

def main():

    all_rows = []
    missing = []

    for ticker in TICKERS:

        print(f"Lade {ticker} ...")

        df = yf.download(
            ticker,
            start=HISTORY_START,
            end=EXIT_DATE,
            interval="1wk",
            progress=False
        )

        if df.empty:
            print(f"❌ Keine Daten für {ticker}")
            missing.append(ticker)
            continue

        df = add_indicators(df)
        trades = run_strategy(df, ticker)
        all_rows.extend(trades)

    if not all_rows:
        print("❌ Keine Trades erzeugt.")
        return

    out = pd.DataFrame(all_rows, columns=["Ticker","Type","Date","Price","Return_%"])
    out["Date"] = pd.to_datetime(out["Date"]).dt.strftime("%d.%m.%Y")
    out.to_excel(OUTPUT_FILE, index=False)

    print(f"\nErgebnisse gespeichert in: {OUTPUT_FILE}")

    if missing:
        pd.DataFrame({"Ticker": missing}).to_excel(MISSING_FILE, index=False)
        print(f"Fehlende Ticker gespeichert in: {MISSING_FILE}")


if __name__ == "__main__":
    main()
