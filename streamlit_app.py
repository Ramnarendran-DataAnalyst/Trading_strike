"""Streamlit UI for the settlement-window calculations in prime.py."""

import csv
import io

import pandas as pd
import streamlit as st

from prime import calculate_color_markings, calculate_window, display, to_date


st.set_page_config(page_title="NIFTY Settlement Analyzer", page_icon="📈", layout="wide")


def read_uploaded_csv(uploaded_file):
    content = uploaded_file.getvalue().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    required = {"Date", "Option Type", "Strike Price", "Settlement Price"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise ValueError("Missing required CSV columns: " + ", ".join(sorted(missing)))
    return list(reader)


st.title("NIFTY Settlement Analyzer")
st.caption("Settlement-price window calculated from the latest available date in the uploaded CSV.")

with st.sidebar:
    uploaded_file = st.file_uploader("Upload NSE option CSV", type="csv")
    base_strike = st.number_input("ATM / base strike", min_value=0.0, value=22700.0, step=100.0)
    pre_open_price = st.number_input("Pre-open NIFTY price", min_value=0.0, value=22715.0, step=1.0)
    calculate = st.button("Calculate", type="primary", use_container_width=True)

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

if not calculate:
    st.stop()

try:
    _, result = calculate_window(rows, float(base_strike))
    _, markings = calculate_color_markings(rows, float(pre_open_price), float(base_strike))
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
        "Strike": display(strike),
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

st.subheader("Final processed NIFTY option window")
st.caption(
    f"ITM strikes (pre-open {display(float(pre_open_price))}): "
    f"{display(itm['ce'])} CE, {display(itm['pe'])} PE"
)
st.dataframe(table, hide_index=True, use_container_width=True)

st.subheader("Levels for indicator (copy into TradingView)")


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
st.caption(f"{display(itm['ce'])} CE")
st.code(
    summary_line(
        green.get(itm["ce"]),
        orange.get(itm["ce"]),
        black.get("PE"),
        markings["blue"]["pe"],
    ),
    language=None,
)

st.caption(f"{display(itm['pe'])} PE")
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
    file_name=f"nifty_settlement_window_{latest_date:%Y-%m-%d}_{int(base_strike)}.csv",
    mime="text/csv",
)
