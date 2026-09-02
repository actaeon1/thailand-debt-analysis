"""
ดึง time series หนี้ 3 sector ของไทย (household, non-financial corporate, government)
ปี 2010-2025 จาก IMF Global Debt Database ผ่าน DataMapper API แล้วพล็อตกราฟ

Source: IMF Global Debt Database (Mbaye, Badia & Chae methodology) via DataMapper API
"""

import sys
import requests
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

COUNTRY = "THA"
YEAR_START = 2010
YEAR_END = 2025

INDICATORS = {
    "household": "HH_LS",
    "nfc": "NFC_LS",
    "government": "GG_DEBT_GDP",
}

LABELS = {
    "household": "Household debt",
    "nfc": "Non-financial corporate debt",
    "government": "General government debt",
}

BASE_URL = "https://www.imf.org/external/datamapper/api/v1/{indicator}/{country}"

# BOT/PDMO reported general government debt range for sanity check (% of GDP)
BOT_PDMO_LOW = 59.0
BOT_PDMO_HIGH = 66.0
SANITY_THRESHOLD_PP = 10.0


def fetch_indicator(name: str, code: str) -> dict:
    """Fetch one indicator series for THA from IMF DataMapper API.

    Returns dict: {"series": {year:int -> value:float}, "estimatesStart": int|None}
    Raises RuntimeError with a clear message on any failure (no silent fail).
    """
    url = BASE_URL.format(indicator=code, country=COUNTRY)
    try:
        resp = requests.get(url, timeout=30)
    except requests.RequestException as e:
        raise RuntimeError(
            f"[{name} / {code}] request failed: could not reach {url} ({e})"
        )

    if resp.status_code == 404:
        raise RuntimeError(
            f"[{name} / {code}] HTTP 404 — indicator/country not found at {url}"
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"[{name} / {code}] HTTP {resp.status_code} from {url}: {resp.text[:300]}"
        )

    try:
        payload = resp.json()
    except ValueError:
        raise RuntimeError(
            f"[{name} / {code}] response was not valid JSON from {url}"
        )

    if not payload:
        raise RuntimeError(f"[{name} / {code}] empty JSON payload from {url}")

    values = payload.get("values")
    if not values:
        raise RuntimeError(
            f"[{name} / {code}] no 'values' key in response from {url}. "
            f"Top-level keys were: {list(payload.keys())}"
        )

    if code not in values:
        raise RuntimeError(
            f"[{name} / {code}] indicator code '{code}' missing from response['values']. "
            f"Keys present: {list(values.keys())}"
        )

    country_data = values[code]
    if COUNTRY not in country_data:
        raise RuntimeError(
            f"[{name} / {code}] country key '{COUNTRY}' missing from "
            f"response['values']['{code}']. Countries present: "
            f"{sorted(country_data.keys())[:10]}..."
        )

    series_raw = country_data[COUNTRY]
    if not series_raw:
        raise RuntimeError(
            f"[{name} / {code}] '{COUNTRY}' present but has no data (empty dict)"
        )

    series = {}
    for year_str, val in series_raw.items():
        try:
            year = int(year_str)
        except ValueError:
            continue
        if val is None:
            continue
        if YEAR_START <= year <= YEAR_END:
            series[year] = float(val)

    if not series:
        raise RuntimeError(
            f"[{name} / {code}] no data points in range {YEAR_START}-{YEAR_END}. "
            f"Available years: {sorted(int(y) for y in series_raw if y.isdigit())}"
        )

    estimates_start = payload.get("estimatesStart")
    return {"series": series, "estimatesStart": estimates_start}


def main():
    print("=" * 70)
    print("Fetching IMF Global Debt Database series for Thailand (THA)")
    print("=" * 70)

    fetched = {}
    errors = []
    for name, code in INDICATORS.items():
        try:
            fetched[name] = fetch_indicator(name, code)
            n = len(fetched[name]["series"])
            yrs = sorted(fetched[name]["series"])
            est = fetched[name]["estimatesStart"]
            print(
                f"OK  {name:12s} ({code:12s}): {n} points, "
                f"years {yrs[0]}-{yrs[-1]}, estimatesStart={est}"
            )
        except RuntimeError as e:
            print(f"ERROR fetching {name}: {e}", file=sys.stderr)
            errors.append(str(e))

    if errors:
        raise RuntimeError(
            "Aborting: failed to fetch " + str(len(errors)) +
            " indicator(s):\n" + "\n".join(errors)
        )

    # Build a single DataFrame indexed by year
    all_years = sorted(
        set().union(*(d["series"].keys() for d in fetched.values()))
    )
    df = pd.DataFrame({"year": all_years})
    for name in INDICATORS:
        s = fetched[name]["series"]
        df[name] = df["year"].map(s)

    # Flag projection years per indicator (year >= estimatesStart)
    proj_flags = {}
    for name in INDICATORS:
        est = fetched[name]["estimatesStart"]
        if est is not None:
            proj_flags[name] = df["year"] >= int(est)
        else:
            proj_flags[name] = pd.Series([False] * len(df))
        df[f"{name}_is_projection"] = proj_flags[name]

    # Total non-financial debt = household + nfc + government
    df["total"] = df["household"] + df["nfc"] + df["government"]
    df["total_is_projection"] = (
        df["household_is_projection"]
        | df["nfc_is_projection"]
        | df["government_is_projection"]
    )

    # Print raw table for inspection before trusting the chart
    print()
    print("=" * 70)
    print("RAW DATA TABLE (% of GDP) — inspect before trusting the chart")
    print("=" * 70)
    display_df = df[["year", "household", "nfc", "government", "total"]].copy()
    for name in ["household", "nfc", "government", "total"]:
        proj_col = f"{name}_is_projection"
        display_df[name] = [
            f"{v:.1f}{'*' if p else ''}" if pd.notna(v) else "n/a"
            for v, p in zip(df[name], df[proj_col])
        ]
    with pd.option_context("display.max_rows", None, "display.width", 120):
        print(display_df.to_string(index=False))
    print("(* = IMF projection / estimate year, based on 'estimatesStart' field)")

    # --- Sanity check: government debt vs BOT/PDMO reported range ---
    print()
    print("=" * 70)
    print("SANITY CHECK: IMF GDD general government debt vs BOT/PDMO reported figures")
    print("=" * 70)
    gov_rows = df.dropna(subset=["government"])
    if gov_rows.empty:
        print("WARNING: no government debt data available to sanity-check.")
    else:
        latest_row = gov_rows.iloc[-1]
        latest_year = int(latest_row["year"])
        latest_val = latest_row["government"]
        is_proj = latest_row["government_is_projection"]
        print(
            f"Latest IMF GDD value: {latest_val:.1f}% of GDP "
            f"(year {latest_year}{', PROJECTION' if is_proj else ', actual'})"
        )
        print(f"BOT/PDMO reported range: {BOT_PDMO_LOW}-{BOT_PDMO_HIGH}% of GDP")
        if latest_val < BOT_PDMO_LOW:
            diff = BOT_PDMO_LOW - latest_val
        elif latest_val > BOT_PDMO_HIGH:
            diff = latest_val - BOT_PDMO_HIGH
        else:
            diff = 0.0
        if diff > SANITY_THRESHOLD_PP:
            print(
                f"WARNING: IMF GDD value differs from BOT/PDMO range by "
                f"{diff:.1f}pp (> {SANITY_THRESHOLD_PP}pp threshold). "
                f"This likely reflects a different debt perimeter definition "
                f"(e.g. IMF GDD may include/exclude different government "
                f"sub-sectors, guarantees, or SOE debt compared to BOT/PDMO)."
            )
        else:
            print(
                f"OK: within {SANITY_THRESHOLD_PP}pp of BOT/PDMO reported range "
                f"(diff = {diff:.1f}pp)."
            )

    # --- Plot ---
    plot_chart(df)


def plot_chart(df: pd.DataFrame):
    # Year-over-year change in total debt, for the bottom volume/bar panel
    df = df.sort_values("year").reset_index(drop=True)
    df["total_yoy_change"] = df["total"].diff()

    fig, (ax, ax_bar) = plt.subplots(
        2, 1, figsize=(11, 8.5), sharex=True,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.08},
    )

    # Component lines
    component_styles = {
        "household": {"color": "#4C78A8", "label": LABELS["household"]},
        "nfc": {"color": "#F58518", "label": LABELS["nfc"]},
        "government": {"color": "#54A24B", "label": LABELS["government"]},
    }

    for name, style in component_styles.items():
        actual = df[~df[f"{name}_is_projection"]]
        proj = df[df[f"{name}_is_projection"]]
        ax.plot(
            df["year"], df[name],
            color=style["color"], linewidth=2, label=style["label"],
            marker="o", markersize=4, zorder=3,
        )
        if not proj.empty:
            ax.scatter(
                proj["year"], proj[name],
                facecolors="none", edgecolors=style["color"],
                marker="D", s=70, linewidths=1.8, zorder=4,
            )

    # Total line — thicker, darker
    ax.plot(
        df["year"], df["total"],
        color="#222222", linewidth=3.2, label="Total non-financial debt",
        marker="o", markersize=5, zorder=5,
    )
    proj_total = df[df["total_is_projection"]]
    if not proj_total.empty:
        ax.scatter(
            proj_total["year"], proj_total["total"],
            facecolors="none", edgecolors="#222222",
            marker="D", s=90, linewidths=2.0, zorder=6,
            label="IMF projection",
        )

    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_locator(MultipleLocator(10))
    ax.set_ylabel("% of GDP")
    ax.set_title(
        "Thailand Debt by Sector, 2010–2025\n"
        "Source: IMF Global Debt Database via DataMapper API",
        fontsize=13, fontweight="bold",
    )
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", frameon=True, fontsize=9)
    ax.tick_params(labelbottom=False)  # x labels shown only on bottom panel

    # --- Bottom panel: YoY change in total debt (volume-style bar chart) ---
    INCREASE_COLOR = "#D62728"  # debt rising
    DECREASE_COLOR = "#2CA02C"  # debt falling
    bar_data = df.dropna(subset=["total_yoy_change"])
    colors = [
        INCREASE_COLOR if v >= 0 else DECREASE_COLOR
        for v in bar_data["total_yoy_change"]
    ]
    ax_bar.bar(
        bar_data["year"], bar_data["total_yoy_change"],
        color=colors, width=0.7, zorder=3,
    )
    ax_bar.axhline(0, color="#555555", linewidth=0.8, zorder=2)
    ax_bar.set_ylabel("YoY Δ total debt\n(pp of GDP)", fontsize=9)
    ax_bar.set_xlabel("Year")
    ax_bar.grid(True, axis="y", alpha=0.3)
    ax_bar.yaxis.set_major_locator(MultipleLocator(10))

    from matplotlib.patches import Patch
    ax_bar.legend(
        handles=[
            Patch(color=INCREASE_COLOR, label="Debt increase (YoY)"),
            Patch(color=DECREASE_COLOR, label="Debt decrease (YoY)"),
        ],
        loc="upper right", frameon=True, fontsize=8,
    )

    all_years = df["year"].tolist()
    ax_bar.set_xticks(all_years)
    ax_bar.set_xticklabels([str(int(y)) for y in all_years], rotation=0)

    fig.tight_layout()

    out_path = "D:/investment/Finance_tools/thailand_debt_imf.png"
    fig.savefig(out_path, dpi=150)
    print()
    print(f"Chart saved to: {out_path}")


if __name__ == "__main__":
    main()
