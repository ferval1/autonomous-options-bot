
# Autonomous Options Paper Bot

This is a **paper-trading simulator**, not a live trading bot. It does not connect to Webull and cannot place real orders.

## Run from a computer or cloud workspace

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open the local URL shown by Streamlit.

## Phone-only route

1. Create a GitHub repository.
2. Upload `app.py` and `requirements.txt`.
3. Deploy the repository on Streamlit Community Cloud.
4. Open the resulting web app from your phone.

The app is designed to be paper-only. Keep automatic entries disabled at first.

## Important limitations

- Market data comes from Yahoo Finance, not Webull.
- The option value is theoretical, using a simplified Black–Scholes model.
- It does not represent live bid/ask prices.
- It does not model slippage, commissions, early exercise, assignment, dividends, volatility changes, or market gaps.
- It does not guarantee the daily loss limit can never be exceeded.
- Do not add Webull API credentials until the strategy has been thoroughly tested in a sandbox and the execution controls have been independently reviewed.

## Suggested testing sequence

1. Run with automatic entries OFF.
2. Scan the symbols and inspect signals.
3. Open a few manual paper positions.
4. Test take-profit, stop-loss, and time exits.
5. Test exposure and daily-loss blocking.
6. Record at least 50–100 simulated trades before considering further development.
