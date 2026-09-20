
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timezone
from math import log, sqrt, exp
from statistics import NormalDist

st.set_page_config(page_title="Autonomous Options Paper Bot", layout="wide")

# ---------------- Settings ----------------
DEFAULT_SYMBOLS = ["AMZN","MSFT","NVDA","TSLA","NFLX","SPY","META","QQQ","AAPL","BTC-USD"]

st.title("🤖 Autonomous Options Paper Bot")
st.caption("Simulation only — no live orders, no Webull connection, no real money.")

with st.sidebar:
    st.header("Risk controls")
    starting_cash = st.number_input("Starting paper cash ($)", min_value=100.0, value=700.0, step=50.0)
    max_exposure = st.number_input("Maximum open exposure ($)", min_value=25.0, value=700.0, step=25.0)
    daily_loss_limit = st.number_input("Daily loss limit ($)", min_value=10.0, value=200.0, step=10.0)
    risk_per_trade = st.number_input("Max planned risk per trade ($)", min_value=5.0, value=35.0, step=5.0)
    take_profit = st.slider("Take profit (%)", 10, 200, 50, 5) / 100
    stop_loss = st.slider("Stop loss (%)", 5, 90, 25, 5) / 100
    max_hold_days = st.slider("Maximum holding days", 1, 5, 3)
    iv = st.slider("Assumed implied volatility (%)", 15, 120, 45, 5) / 100
    auto_scan = st.checkbox("Enable automatic paper entries", value=False)
    st.warning("Keep automatic entries OFF until you understand the signals and test several sessions.")

# Session state
if "cash" not in st.session_state:
    st.session_state.cash = float(starting_cash)
if "positions" not in st.session_state:
    st.session_state.positions = []
if "closed" not in st.session_state:
    st.session_state.closed = []
if "day_start" not in st.session_state:
    st.session_state.day_start = datetime.now().date().isoformat()
if "realized_today" not in st.session_state:
    st.session_state.realized_today = 0.0

if st.button("Reset simulation"):
    for key in ["cash","positions","closed","day_start","realized_today"]:
        st.session_state.pop(key, None)
    st.rerun()

# ---------------- Helpers ----------------
def norm_cdf(x):
    return NormalDist().cdf(x)

def bs_price(S, K, T, r, sigma, kind):
    if T <= 0:
        return max(0.0, S-K) if kind == "CALL" else max(0.0, K-S)
    if S <= 0 or K <= 0 or sigma <= 0:
        return 0.0
    d1 = (log(S/K) + (r + 0.5*sigma*sigma)*T) / (sigma*sqrt(T))
    d2 = d1 - sigma*sqrt(T)
    if kind == "CALL":
        return S*norm_cdf(d1) - K*exp(-r*T)*norm_cdf(d2)
    return K*exp(-r*T)*norm_cdf(-d2) - S*norm_cdf(-d1)

def get_data(symbol):
    data = yf.download(symbol, period="3mo", interval="1d", auto_adjust=False, progress=False)
    if data is None or data.empty:
        return None
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    data = data.dropna()
    if len(data) < 40:
        return None
    close = data["Close"].astype(float)
    data["EMA9"] = close.ewm(span=9, adjust=False).mean()
    data["EMA21"] = close.ewm(span=21, adjust=False).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    data["RSI"] = 100 - (100 / (1 + rs))
    tr = pd.concat([
        data["High"] - data["Low"],
        (data["High"] - data["Close"].shift()).abs(),
        (data["Low"] - data["Close"].shift()).abs()
    ], axis=1).max(axis=1)
    data["ATR"] = tr.rolling(14).mean()
    return data.dropna()

def signal_for(data):
    last = data.iloc[-1]
    if last["EMA9"] > last["EMA21"] and 45 <= last["RSI"] <= 68:
        return "CALL", "Bullish trend + RSI filter"
    if last["EMA9"] < last["EMA21"] and 32 <= last["RSI"] <= 55:
        return "PUT", "Bearish trend + RSI filter"
    return "NONE", "No qualifying setup"

def current_price(symbol):
    data = get_data(symbol)
    if data is None:
        return None, None, None
    last = data.iloc[-1]
    return float(last["Close"]), data, last

def mark_positions():
    total_unrealized = 0.0
    updated = []
    for p in st.session_state.positions:
        price, data, last = current_price(p["symbol"])
        if price is None:
            updated.append(p)
            continue
        days_held = (datetime.now().date() - datetime.fromisoformat(p["opened"]).date()).days
        T = max((p["dte"] - days_held) / 365, 1/3650)
        theoretical = bs_price(price, p["strike"], T, 0.04, p["iv"], p["kind"])
        value = theoretical * 100 * p["contracts"]
        pnl = value - p["cost"]
        p["underlying_now"] = price
        p["mark_value"] = value
        p["pnl"] = pnl
        p["days_held"] = days_held
        total_unrealized += pnl
        updated.append(p)
    st.session_state.positions = updated
    return total_unrealized

def close_position(index, reason):
    p = st.session_state.positions.pop(index)
    proceeds = max(0.0, p.get("mark_value", 0.0))
    pnl = proceeds - p["cost"]
    st.session_state.cash += proceeds
    st.session_state.realized_today += pnl
    p["closed"] = datetime.now().isoformat(timespec="seconds")
    p["exit_reason"] = reason
    p["realized_pnl"] = pnl
    st.session_state.closed.append(p)

# ---------------- Scan ----------------
symbols_text = st.text_input("Symbols to scan (comma separated)", ",".join(DEFAULT_SYMBOLS))
symbols = [s.strip().upper() for s in symbols_text.split(",") if s.strip()]

if st.session_state.day_start != datetime.now().date().isoformat():
    st.session_state.day_start = datetime.now().date().isoformat()
    st.session_state.realized_today = 0.0

unrealized = mark_positions()
open_exposure = sum(p["cost"] for p in st.session_state.positions)
equity = st.session_state.cash + sum(p.get("mark_value", 0) for p in st.session_state.positions)

c1,c2,c3,c4 = st.columns(4)
c1.metric("Paper equity", f"${equity:,.2f}")
c2.metric("Cash", f"${st.session_state.cash:,.2f}")
c3.metric("Open exposure", f"${open_exposure:,.2f}")
c4.metric("Today's realized P/L", f"${st.session_state.realized_today:,.2f}")

st.subheader("Market scan")
rows = []
for symbol in symbols:
    try:
        price, data, last = current_price(symbol)
        if data is None:
            continue
        sig, reason = signal_for(data)
        rows.append({
            "Symbol": symbol,
            "Price": round(price, 2),
            "EMA9": round(float(last["EMA9"]), 2),
            "EMA21": round(float(last["EMA21"]), 2),
            "RSI": round(float(last["RSI"]), 1),
            "ATR": round(float(last["ATR"]), 2),
            "Signal": sig,
            "Reason": reason
        })
    except Exception as e:
        rows.append({"Symbol": symbol, "Signal": "ERROR", "Reason": str(e)})

scan_df = pd.DataFrame(rows)
st.dataframe(scan_df, use_container_width=True, hide_index=True)

# ---------------- Automatic paper entries ----------------
if auto_scan and not scan_df.empty:
    if st.session_state.realized_today <= -daily_loss_limit:
        st.error("Daily loss limit reached. New entries are blocked.")
    else:
        for _, row in scan_df.iterrows():
            if row.get("Signal") not in ["CALL","PUT"]:
                continue
            if any(p["symbol"] == row["Symbol"] for p in st.session_state.positions):
                continue
            if open_exposure >= max_exposure:
                break
            S = float(row["Price"])
            kind = row["Signal"]
            strike = round(S * (1.01 if kind=="CALL" else 0.99), 0)
            dte = max_hold_days
            premium = bs_price(S, strike, dte/365, 0.04, iv, kind)
            cost = premium * 100
            if cost <= 0 or cost > risk_per_trade or open_exposure + cost > max_exposure:
                continue
            st.session_state.positions.append({
                "symbol": row["Symbol"], "kind": kind, "strike": strike,
                "dte": dte, "iv": iv, "contracts": 1, "cost": cost,
                "opened": datetime.now().isoformat(timespec="seconds"),
                "underlying_entry": S, "mark_value": cost, "pnl": 0.0
            })
            st.session_state.cash -= cost
        st.rerun()

# ---------------- Position management ----------------
st.subheader("Open paper positions")
if st.session_state.positions:
    for i, p in enumerate(st.session_state.positions):
        pnl_pct = (p.get("pnl",0) / p["cost"]) if p["cost"] else 0
        st.write(
            f"**{p['symbol']} {p['kind']}** | Strike ${p['strike']:.2f} | "
            f"Cost ${p['cost']:.2f} | Mark ${p.get('mark_value',0):.2f} | "
            f"P/L ${p.get('pnl',0):.2f} ({pnl_pct:.1%}) | Held {p.get('days_held',0)} day(s)"
        )
        reason = None
        if pnl_pct >= take_profit:
            reason = "Take profit"
        elif pnl_pct <= -stop_loss:
            reason = "Stop loss"
        elif p.get("days_held",0) >= max_hold_days:
            reason = "Time exit"
        if reason:
            st.warning(f"{p['symbol']} triggered: {reason}")
            if st.button(f"Close {p['symbol']} #{i}", key=f"close_{i}"):
                close_position(i, reason)
                st.rerun()
else:
    st.info("No open paper positions.")

# ---------------- Manual test entry ----------------
st.subheader("Manual paper test")
with st.form("manual_entry"):
    a,b,c,d = st.columns(4)
    symbol = a.selectbox("Symbol", symbols if symbols else DEFAULT_SYMBOLS)
    kind = b.selectbox("Type", ["CALL","PUT"])
    strike = c.number_input("Strike", min_value=0.01, value=100.0, step=1.0)
    premium = d.number_input("Premium per share", min_value=0.01, value=0.20, step=0.05)
    contracts = st.number_input("Contracts", min_value=1, max_value=10, value=1, step=1)
    submitted = st.form_submit_button("Open paper position")
    if submitted:
        cost = premium * 100 * contracts
        if st.session_state.realized_today <= -daily_loss_limit:
            st.error("Daily loss limit reached.")
        elif open_exposure + cost > max_exposure:
            st.error("Exposure limit would be exceeded.")
        elif cost > risk_per_trade:
            st.error("Cost exceeds max planned risk per trade.")
        else:
            price, _, _ = current_price(symbol)
            st.session_state.positions.append({
                "symbol": symbol, "kind": kind, "strike": strike, "dte": max_hold_days,
                "iv": iv, "contracts": int(contracts), "cost": cost,
                "opened": datetime.now().isoformat(timespec="seconds"),
                "underlying_entry": price, "mark_value": cost, "pnl": 0.0
            })
            st.session_state.cash -= cost
            st.success("Paper position opened.")
            st.rerun()

# ---------------- Closed trades ----------------
st.subheader("Closed paper trades")
if st.session_state.closed:
    st.dataframe(pd.DataFrame(st.session_state.closed), use_container_width=True, hide_index=True)
else:
    st.info("No closed trades yet.")

st.divider()
st.caption("Educational simulator. The theoretical option mark uses Black–Scholes assumptions and is not a live option quote. It does not model bid/ask spreads, early exercise, assignment, dividends, volatility changes, or real Webull execution.")
