import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

# ==========================================================
# 1. FESTES AKTIEN-UNIVERSUM
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

print(f"✅ Universum geladen: {len(TICKERS)} Aktien")

# ==========================================================
# 2. ZEITRAUM & OUTPUT
# ==========================================================

BACKTEST_START = pd.Timestamp("2018-01-01")
EXIT_DATE      = pd.Timestamp.today().normalize()
HISTORY_START  = pd.Timestamp("2016-01-01")  # genug Historie für SMA200 im Weekly

timestamp    = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_FILE  = f"nasdaq_weekly_3stocks_20241220_trades_{timestamp}.xlsx"
MISSING_FILE = f"nasdaq_weekly_3stocks_20241220_missing_{timestamp}.xlsx"

# ==========================================================
# 3. INDIKATOREN (1D-SICHER)
# ==========================================================

def add_indicators(df):

    close = df["Close"].iloc[:, 0] if isinstance(df["Close"], pd.DataFrame) else df["Close"]
    high  = df["High"].iloc[:, 0]  if isinstance(df["High"], pd.DataFrame)  else df["High"]
    low   = df["Low"].iloc[:, 0]   if isinstance(df["Low"], pd.DataFrame)   else df["Low"]

    close = close.astype(float)
    high  = high.astype(float)
    low   = low.astype(float)

    # EMAs
    df["ema50"]  = close.ewm(span=50,  adjust=False).mean()
    df["ema100"] = close.ewm(span=100, adjust=False).mean()
    df["ema200"] = close.ewm(span=200, adjust=False).mean()

    # SMAs
    df["sma20"]  = close.rolling(20).mean()
    df["sma50"]  = close.rolling(50).mean()
    df["sma200"] = close.rolling(200).mean()

    # ATR
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low  - close.shift(1)).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1/14, adjust=False).mean()

    # ADX
    up   = high.diff()
    down = -low.diff()

    plus_dm  = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)

    plus  = plus_dm.ewm(alpha=1/14, adjust=False).mean()
    minus = minus_dm.ewm(alpha=1/14, adjust=False).mean()

    plus_di  = 100 * plus  / df["atr"]
    minus_di = 100 * minus / df["atr"]

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df["adx"] = dx.ewm(alpha=1/14, adjust=False).mean()

    # SMA200-Slope
    df["slope"] = df["sma200"] - df["sma200"].shift(10)

    # Trendstabilität
    cond = df["sma20"] < df["sma50"]
    bars_since = []
    last_true = None

    for i, v in enumerate(cond):
        if v:
            last_true = i
            bars_since.append(0)
        else:
            bars_since.append(np.nan if last_true is None else i - last_true)

    df["bars_since"] = bars_since

    return df


# ==========================================================
# 4. STRATEGIE
# ==========================================================

def run_strategy(df, ticker):

    rows = []
    position = False
    entry_price = 0.0
    entry_date = None
    cooldown = -1

    close = df["Close"].astype(float).values

    for i in range(len(df)):

        if df.index[i] < BACKTEST_START:
            continue

        # ==========================================================
        # EXIT – NACH ENTRY AUF DAILY WECHSELN
        # ==========================================================
        if position:

            # Daily-Daten nur einmal laden
            if "daily_df" not in locals():
                daily_df = yf.download(
                    ticker,
                    start=entry_date - pd.Timedelta(days=5),
                    end=EXIT_DATE,
                    interval="1d",
                    progress=False
                )

                daily_df["ema50"]  = daily_df["Close"].ewm(span=50).mean()
                daily_df["ema100"] = daily_df["Close"].ewm(span=100).mean()
                daily_df["ema200"] = daily_df["Close"].ewm(span=200).mean()

                daily_start_idx = daily_df.index.get_loc(entry_date, method="bfill")

            # Bestimme wie viele Tage die Position offen ist
            today_idx = daily_df.index.get_indexer([df.index[i]], method="ffill")[0]
            days_open = today_idx - daily_start_idx

            # Welcher EMA ist aktiv?
            if days_open <= 50:
                critical_ema = "ema200"
            elif days_open <= 100:
                critical_ema = "ema100"
            else:
                critical_ema = "ema50"

            # Exit-Bedingung täglich
            daily_close = daily_df["Close"].iloc[today_idx]
            daily_crit  = daily_df[critical_ema].iloc[today_idx]

            if daily_close < daily_crit:

                exit_price = float(close[i])
                exit_date  = df.index[i]
                ret_pct    = (exit_price / entry_price - 1) * 100

                rows.append([ticker, "EXIT", exit_date, exit_price, ret_pct])

                position = False
                entry_price = 0.0
                entry_date = None
                cooldown = i + 15
                daily_df = None  # Reset für nächste Position
                continue

        # ==========================================================
        # ENTRY (weiterhin WEEKLY)
        # ==========================================================
        if not position and i > cooldown:

            if (
                close[i] > df["sma200"].iloc[i] and
                df["sma20"].iloc[i] > df["sma50"].iloc[i] and
                df["adx"].iloc[i] > 20 and
                df["slope"].iloc[i] > 0 and
                abs(df["ema50"].iloc[i] - df["ema200"].iloc[i]) / close[i] > 0.01 and
                df["atr"].iloc[i] / close[i] > 0.005 and
                df["bars_since"].iloc[i] > 5
            ):
                position = True
                entry_price = float(close[i])
                entry_date = df.index[i]

                # Daily-DF reset für neue Position
                if "daily_df" in locals():
                    del daily_df

                rows.append([ticker, "ENTRY", entry_date, entry_price, ""])

    # ==========================================================
    # FORCED EXIT BEI BACKTEST-ENDE
    # ==========================================================
    if position:
        exit_price = float(close[-1])
        exit_date  = EXIT_DATE
        ret_pct    = (exit_price / entry_price - 1) * 100
        rows.append([ticker, "EXIT", exit_date, exit_price, ret_pct])

    return rows


# ==========================================================
# 5. LAUF & EXCEL
# ==========================================================

def main():

    all_rows = []
    missing  = []

    for ticker in TICKERS:

        print(f"▶ Lade {ticker}")

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
        rows_out = run_strategy(df, ticker)
        all_rows.extend(rows_out)

    if not all_rows:
        print("❌ Keine Trades erzeugt.")
        return

    result = pd.DataFrame(
        all_rows,
        columns=["Ticker", "Type", "Date", "Price", "Return_%"]
    )

    result["Date"] = pd.to_datetime(result["Date"]).dt.strftime("%d.%m.%Y")
    result.to_excel(OUTPUT_FILE, index=False)

    print(f"\n✅ Excel erstellt: {OUTPUT_FILE}")

    if missing:
        pd.DataFrame({"Ticker": missing}).to_excel(MISSING_FILE, index=False)
        print(f"⚠ Fehlende Ticker gespeichert in: {MISSING_FILE}")


if __name__ == "__main__":
    main()
