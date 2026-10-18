#!/usr/bin/env python3
"""Create a NIFTY CE/PE settlement-price window from an NSE option CSV.

The script finds the latest Date in the CSV automatically. For the entered
base strike it uses the four listed strikes above and below it, then prints
CE, PE, CE + PE, and their average for every strike in that nine-strike window.

When a pre-open price is supplied, it also produces the Green, Orange, Blue,
and Black groups shown in the reference table.
"""

from __future__ import annotations

import argparse
import csv
import sys
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from pathlib import Path


DEFAULT_CSV = Path(
    r"C:\Users\Ramnarendran\Downloads\Quote-Derivative-NIFTY-14-09-2026-14-10-2026.csv"
)

DATE_FORMAT = "%d-%b-%Y"


def to_number(value: str) -> float | None:
    """Convert NSE-formatted values such as '23,400.00' to a number."""
    try:
        return float((value or "").replace(",", "").strip())
    except ValueError:
        return None


def to_date(value: str):
    """Parse dates used by NSE exports."""
    value = (value or "").strip()
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def display(value: float | None) -> str:
    """Format outputs as whole numbers with conventional half-up rounding."""
    if value is None:
        return "—"
    return str(int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)))


def is_hundred_strike(strike: float) -> bool:
    """Keep 100-point strikes such as 22600 and 22700 only."""
    return abs(strike - round(strike / 100) * 100) < 0.001


def read_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        required = {"Date", "Option Type", "Strike Price", "Settlement Price"}
        found = set(reader.fieldnames or [])
        missing = required - found
        if missing:
            raise ValueError("Missing required CSV columns: " + ", ".join(sorted(missing)))
        return list(reader)


def latest_option_data(rows: list[dict[str, str]]):
    """Return latest-date settlement prices keyed by (strike, CE/PE)."""
    dates = [to_date(row["Date"]) for row in rows]
    valid_dates = [item for item in dates if item is not None]
    if not valid_dates:
        raise ValueError("The Date column has no valid dates.")

    latest_date = max(valid_dates)
    latest_rows = [row for row in rows if to_date(row["Date"]) == latest_date]

    prices: dict[tuple[float, str], float] = {}
    strikes: set[float] = set()
    for row in latest_rows:
        strike = to_number(row["Strike Price"])
        settlement = to_number(row["Settlement Price"])
        option_type = row["Option Type"].strip().upper()
        if strike is None:
            continue
        if not is_hundred_strike(strike):
            continue
        strikes.add(strike)
        if option_type in {"CE", "PE"} and settlement is not None:
            prices[(strike, option_type)] = settlement

    ordered_strikes = sorted(strikes)
    return latest_date, prices, ordered_strikes


def calculate_window(rows: list[dict[str, str]], base_strike: float):
    """Calculate the CE/PE total and average for the nine-strike window."""
    latest_date, prices, ordered_strikes = latest_option_data(rows)
    if base_strike not in ordered_strikes:
        nearest = sorted(ordered_strikes, key=lambda strike: abs(strike - base_strike))[:5]
        nearby = ", ".join(display(strike) for strike in sorted(nearest))
        raise ValueError(
            f"Strike {display(base_strike)} is unavailable on {latest_date:%d-%b-%Y}. "
            f"Nearby available strikes: {nearby}"
        )

    base_index = ordered_strikes.index(base_strike)
    window = ordered_strikes[max(0, base_index - 4) : base_index + 5]
    if len(window) != 9:
        raise ValueError("There are not four available strikes on both sides of the chosen strike.")

    result = []
    for strike in reversed(window):  # highest strike first, matching the reference image
        ce = prices.get((strike, "CE"))
        pe = prices.get((strike, "PE"))
        total = ce + pe if ce is not None and pe is not None else None
        average = total / 2 if total is not None else None
        result.append((strike, ce, pe, total, average))
    return latest_date, result


def calculate_color_markings(
    rows: list[dict[str, str]], pre_open_price: float, base_strike: float | None = None
):
    """Return the screenshot-style Green, Orange, Blue, and Black groups.

    Rule supplied for the color groups:
    - Green: CE at the strike at/below pre-open and PE at the next strike above.
    - Orange: the CE+PE average (prime value) at each Green strike.
    - Blue CE: up to three CE values immediately greater than the Green PE value.
    - Blue PE: up to three PE values immediately greater than the Green CE value.
    - Black CE: the closest CE value lower than the Green PE value.
    - Black PE: the closest PE value lower than the Green CE value.

    Returned entries retain their strike and option side so each displayed value
    can be traced back to the source data.
    """
    latest_date, prices, ordered_strikes = latest_option_data(rows)
    if base_strike is not None:
        if base_strike not in ordered_strikes:
            raise ValueError(f"Base strike {display(base_strike)} is unavailable in the latest-date data.")
        base_index = ordered_strikes.index(base_strike)
        displayed_strikes = set(ordered_strikes[max(0, base_index - 4): base_index + 5])
        if len(displayed_strikes) != 9:
            raise ValueError("There are not four available strikes on both sides of the chosen strike.")
        prices = {
            (strike, option_type): value
            for (strike, option_type), value in prices.items()
            if strike in displayed_strikes
        }
        ordered_strikes = sorted(displayed_strikes)
    ce_candidates = [strike for strike in ordered_strikes if strike <= pre_open_price and (strike, "CE") in prices]
    pe_candidates = [strike for strike in ordered_strikes if strike > pre_open_price and (strike, "PE") in prices]
    if not ce_candidates or not pe_candidates:
        raise ValueError("Could not find both pre-open ITM strikes in the latest-date data.")

    ce_strike = max(ce_candidates)
    pe_strike = min(pe_candidates)
    def item(strike: float, option_type: str):
        value = prices.get((strike, option_type))
        if value is None:
            return None
        return {"strike": strike, "option_type": option_type, "value": value}

    def prime_value(strike: float):
        ce = prices.get((strike, "CE"))
        pe = prices.get((strike, "PE"))
        if ce is None or pe is None:
            return None
        return {"strike": strike, "value": (ce + pe) / 2}

    green_ce_value = prices[(ce_strike, "CE")]
    green_pe_value = prices[(pe_strike, "PE")]

    def values_for(option_type: str):
        return [
            {"strike": strike, "option_type": option_type, "value": value}
            for (strike, side), value in prices.items()
            if side == option_type
        ]

    def nearest_higher(option_type: str, threshold: float, limit: int = 3):
        """Return the smallest option prices strictly above a threshold."""
        return sorted(
            (entry for entry in values_for(option_type) if entry["value"] > threshold),
            key=lambda entry: (entry["value"], entry["strike"]),
        )[:limit]

    def nearest_lower(option_type: str, threshold: float):
        """Return the option price immediately below a threshold."""
        candidates = [entry for entry in values_for(option_type) if entry["value"] < threshold]
        return max(candidates, key=lambda entry: (entry["value"], entry["strike"])) if candidates else None

    return latest_date, {
        "itm_strikes": {"ce": ce_strike, "pe": pe_strike},
        "green": [item(pe_strike, "PE"), item(ce_strike, "CE")],
        "orange": [prime_value(pe_strike), prime_value(ce_strike)],
        "blue": {
            "ce": nearest_higher("CE", green_pe_value),
            "pe": nearest_higher("PE", green_ce_value),
        },
        "black": [
            entry for entry in (
                nearest_lower("CE", green_pe_value),
                nearest_lower("PE", green_ce_value),
            ) if entry is not None
        ],
    }


def print_table(latest_date, base_strike: float, result) -> None:
    print(f"Latest data date used: {latest_date:%d-%b-%Y}")
    print(f"ATM strike base: {display(base_strike)}\n")
    print("Final processed NIFTY option window")
    print(f"{'Strike':>8}  {'CE':>10}  {'PE':>10}  {'Total (CE + PE)':>16}  {'Average':>10}")
    print("-" * 62)
    for strike, ce, pe, total, average in result:
        print(
            f"{display(strike):>8}  {display(ce):>10}  {display(pe):>10}  "
            f"{display(total):>16}  {display(average):>10}"
        )


def print_color_markings(latest_date, markings) -> None:
    """Print the screenshot-style color classifications with source strikes."""
    itm = markings["itm_strikes"]
    print(f"\nColor markings for latest date: {latest_date:%d-%b-%Y}")
    print(f"ITM strikes (pre-open): {display(itm['ce'])} CE, {display(itm['pe'])} PE")
    for color in ("green", "orange", "black"):
        values = markings[color]
        label = ", ".join(
            f"{display(entry['value'])} ({display(entry['strike'])} {entry.get('option_type', 'Prime')})"
            for entry in values if entry is not None
        )
        print(f"{color.title()}: {label}")
    for side, values in markings["blue"].items():
        label = ", ".join(f"{display(entry['value'])} ({display(entry['strike'])} {side.upper()})" for entry in values)
        print(f"Blue {side.upper()}: {label}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("strike", nargs="?", type=float, help="Base/ATM strike, for example 22700")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="Path to the NSE CSV file")
    parser.add_argument("--pre-open", type=float, help="Pre-open NIFTY price for Green/Orange/Blue/Black groups")
    args = parser.parse_args()

    try:
        base_strike = args.strike
        if base_strike is None:
            base_strike = to_number(input("Enter base strike: "))
        if base_strike is None:
            raise ValueError("Enter a valid numeric strike.")
        rows = read_rows(args.csv)
        latest_date, result = calculate_window(rows, base_strike)
        print_table(latest_date, base_strike, result)
        if args.pre_open is not None:
            color_date, markings = calculate_color_markings(rows, args.pre_open, base_strike)
            print_color_markings(color_date, markings)
        return 0
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
