"""Streamlit UI for the settlement-window calculations in prime.py."""

import csv
import io

import pandas as pd
import streamlit as st

from prime import (
    calculate_color_markings,
    calculate_window,
    display,
    display_strike,
    latest_option_data,
    to_date,
)


st.set_page_config(page_title="Option Settlement Analyzer", page_icon="📈", layout="wide")


def read_uploaded_csv(uploaded_file):
    content = uploaded_file.getvalue().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    required = {"Date", "Option Type", "Strike Price", "Settlement Price"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise ValueError("Missing required CSV columns: " + ", ".join(sorted(missing)))
    return list(reader)


st.title("Option Settlement Analyzer")
st.caption("Settlement-price window calculated from the latest available date in the uploaded NSE option CSV.")

with st.sidebar:
    uploaded_file = st.file_uploader("Upload NSE option CSV", type="csv")
    option_market = st.radio("Option type", ("NIFTY index option", "Stock option"))

if uploaded_file is None:
    st.info("Upload the NSE option CSV to calculate the nine-strike window.")
    st.stop()

try:
    rows = read_uploaded_csv(uploaded_file)
    latest_date = max(to_date(row["Date"]) for row in rows if to_date(row["Date"]) is not None)
except (UnicodeDecodeError, ValueError) as error:
    st.error(f"Could not read the CSV: {error}")
    st.stop()

st.write(f"**Latest data date used:** {latest_date:%d-%b-%Y}")

strike_step = 100.0 if option_market == "NIFTY index option" else None
_, _, available_strikes = latest_option_data(rows, strike_step)
if not available_strikes:
    st.error("No valid strikes were found for the selected option type.")
    st.stop()

default_strike = 22700.0 if option_market == "NIFTY index option" else available_strikes[len(available_strikes) // 2]
if default_strike not in available_strikes:
    default_strike = available_strikes[len(available_strikes) // 2]
strike_increment = 100.0 if option_market == "NIFTY index option" else 1.0

with st.sidebar:
    base_strike = st.number_input(
        "ATM / base strike",
        min_value=0.0,
        value=float(default_strike),
        step=strike_increment,
        help="NIFTY mode uses 100-point strikes. Stock-option mode uses every strike listed in the CSV.",
    )
    pre_open_price = st.number_input(
        "Pre-open underlying price", min_value=0.0, value=float(default_strike), step=1.0
    )
    calculate = st.button("Calculate", type="primary", use_container_width=True)

if not calculate:
    st.stop()

try:
    _, result = calculate_window(rows, float(base_strike), strike_step)
    _, markings = calculate_color_markings(
        rows, float(pre_open_price), float(base_strike), strike_step
    )
except ValueError as error:
    st.error(str(error))
    st.stop()

green = {entry["strike"]: entry["value"] for entry in markings["green"] if entry is not None}
orange = {entry["strike"]: entry["value"] for entry in markings["orange"] if entry is not None}
black = {entry["option_type"]: entry["value"] for entry in markings["black"]}
itm = markings["itm_strikes"]


def joined(values):
    return ", ".join(display(entry["value"]) for entry in values)


table_rows = []
for strike, ce, pe, total, average in result:
    row = {
        "Strike": display_strike(strike),
        "CE": display(ce),
        "PE": display(pe),
        "Total (CE + PE)": display(total),
        "Prime Value": display(average),
        "Green": display(green[strike]) if strike in green else "",
        "Orange": display(orange[strike]) if strike in orange else "",
        "Blue": "",
        "Black": "",
    }
    # Position values in the same two rows as the supplied reference table.
    if strike == itm["pe"]:
        row["Blue"] = joined(markings["blue"]["ce"])
        row["Black"] = display(black.get("CE"))
    elif strike == itm["ce"]:
        row["Blue"] = joined(markings["blue"]["pe"])
        row["Black"] = display(black.get("PE"))
    table_rows.append(row)

table = pd.DataFrame(table_rows)

st.subheader("Final processed option window")
st.caption(
    f"ITM strikes (pre-open {display(float(pre_open_price))}): "
    f"{display_strike(itm['ce'])} CE, {display_strike(itm['pe'])} PE"
)
st.dataframe(table, hide_index=True, use_container_width=True)

st.subheader("Levels for indicator (copy into TradingView)")

with st.expander("How to read the colour levels", expanded=False):
    st.markdown(
        f"""
This app uses the **Settlement Price** on the latest date in the CSV. It first shows nine strikes: your selected strike, four higher strikes, and four lower strikes.

### Step 1: choose the two reference options

Your pre-open underlying price is **{display(float(pre_open_price))}**.

- **{display_strike(itm['ce'])} CE** is the nearest listed Call strike at or below the pre-open price.
- **{display_strike(itm['pe'])} PE** is the nearest listed Put strike above the pre-open price.

These are the headings of the two copy blocks below. Think of each Green value as the reference price for its block.

### Step 2: calculate Green and Orange

- **Green** is the Settlement Price of that reference option.
- **Orange** is the average of the CE and PE Settlement Prices at the same strike: `(CE + PE) ÷ 2`.

### Step 3: calculate Blue and Black

For the **{display_strike(itm['ce'])} CE** block:

- **Blue** lists up to three PE Settlement Prices that are just higher than the Green CE price, beginning with the closest higher price.
- **Black** is the PE Settlement Price immediately below the Green CE price.

For the **{display_strike(itm['pe'])} PE** block:

- **Blue** lists up to three CE Settlement Prices that are just higher than the Green PE price, beginning with the closest higher price.
- **Black** is the CE Settlement Price immediately below the Green PE price.

### Current calculation in this result

**{display_strike(itm['ce'])} CE** starts with Green **{display(green.get(itm['ce']))}**. The app finds PE values above **{display(green.get(itm['ce']))}** for Blue (**{joined(markings['blue']['pe'])}**) and the closest PE value below it for Black (**{display(black.get('PE'))}**). Orange is **{display(orange.get(itm['ce']))}**.

**{display_strike(itm['pe'])} PE** starts with Green **{display(green.get(itm['pe']))}**. The app finds CE values above **{display(green.get(itm['pe']))}** for Blue (**{joined(markings['blue']['ce'])}**) and the closest CE value below it for Black (**{display(black.get('CE'))}**). Orange is **{display(orange.get(itm['pe']))}**.

Only prices from the nine rows in the displayed table are considered. NIFTY mode keeps 100-point strikes only. Stock-option mode uses every strike level listed in the uploaded CSV.
"""
    )


def summary_line(green_value, orange_value, black_value, blue_values):
    return "\n".join(
        (
            f"Green: {display(green_value)}",
            f"Orange: {display(orange_value)}",
            f"Black: {display(black_value)}",
            f"Blue: {joined(blue_values)}",
        )
    )


# Separate blocks make each option's levels easy to copy into TradingView.
st.caption(f"{display_strike(itm['ce'])} CE")
st.code(
    summary_line(
        green.get(itm["ce"]),
        orange.get(itm["ce"]),
        black.get("PE"),
        markings["blue"]["pe"],
    ),
    language=None,
)

st.caption(f"{display_strike(itm['pe'])} PE")
st.code(
    summary_line(
        green.get(itm["pe"]),
        orange.get(itm["pe"]),
        black.get("CE"),
        markings["blue"]["ce"],
    ),
    language=None,
)

st.download_button(
    "Download result as CSV",
    table.to_csv(index=False).encode("utf-8"),
    file_name=f"option_settlement_window_{latest_date:%Y-%m-%d}_{display_strike(float(base_strike))}.csv",
    mime="text/csv",
)
