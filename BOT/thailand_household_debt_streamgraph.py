"""
กราฟชุดที่ 3 (แยกจาก stacked-composition chart เดิม) จากข้อมูลชุดเดียวกัน —
BOT household debt by lender (EC_MB_039 / reportID=775), 2015Q1-2023Q4:

  1) Stream graph (ThemeRiver) — absolute % of GDP ต่อ lender type ตามเวลา
  2) Diverging bar chart — QoQ percentage-point change ของแต่ละ "group"
     (bank / nonbank-near-bank / other), แท่งบวก-ลบรอบแกน 0

หมายเหตุ: ผู้ใช้พิมพ์ว่า "ข้อมูล BOI" — ในบริบทนี้ไม่เคยมี pipeline ดึงข้อมูล BOI
(Board of Investment) เลย ส่วนก่อนหน้าทั้งหมดคือ BOT (Bank of Thailand)
household-debt-by-lender ตีความว่าเป็น typo ของ "BOT" และใช้ข้อมูลชุดเดิมที่ดึง
+ verify ไปแล้วใน thailand_household_debt_by_lender.py (ผลลัพธ์ persist เป็น
CSV ในโฟลเดอร์เดียวกัน — ใช้ต่อได้เลยไม่ต้อง re-fetch)

ทั้ง 2 กราฟนี้เป็นคนละ figure จากกัน และคนละ figure จาก 100%-stacked composition
chart เดิม (thailand_household_debt_lender_breakdown.png) — ไม่รวมกัน เพราะคนละ
มิติ (absolute level ผ่านเวลา vs การเปลี่ยนแปลงต่อ period)
"""

import sys
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

CSV_PATH = "thailand_household_debt_by_lender_pct_gdp.csv"

# same group / color convention as thailand_household_debt_by_lender.py —
# kept in sync manually since this script intentionally doesn't re-derive
# from ROW_MAP (self-contained, reads only the already-verified CSV output)
GROUP_OF = {
    "Commercial banks": "bank",
    "Specialized state banks": "bank",
    "Savings cooperatives": "nonbank",
    "Credit card / leasing / personal loan cos.": "nonbank",
    "Pawnshops": "nonbank",
    "Other deposit-taking institutions": "other",
    "Insurance companies": "other",
    "Securities companies": "other",
    "Asset management companies": "other",
    "Others": "other",
}

BANK_COLORS = {"Commercial banks": "#1f4e8c", "Specialized state banks": "#5b8fd4"}
NONBANK_COLORS = {
    "Credit card / leasing / personal loan cos.": "#c0392b",
    "Pawnshops": "#e67e22",
    "Savings cooperatives": "#f1a208",
}
OTHER_COLORS = {
    "Other deposit-taking institutions": "#95a5a6",
    "Insurance companies": "#7f8c8d",
    "Securities companies": "#bdc3c7",
    "Asset management companies": "#aab7b8",
    "Others": "#d5dbdb",
}
COLOR_OF = {**BANK_COLORS, **NONBANK_COLORS, **OTHER_COLORS}

GROUP_LABEL = {
    "bank": "Bank group (commercial + specialized state banks)",
    "nonbank": "Nonbank/near-bank group (savings coop + credit card/leasing/personal loan + pawnshops)",
    "other": "Other (insurance, securities, asset mgmt, other deposit-taking, misc.)",
}
GROUP_COLOR = {"bank": "#1f4e8c", "nonbank": "#c0392b", "other": "#7f8c8d"}


def load_data() -> pd.DataFrame:
    try:
        df = pd.read_csv(CSV_PATH)
    except FileNotFoundError:
        raise RuntimeError(
            f"ไม่พบ '{CSV_PATH}' — ต้องรัน thailand_household_debt_by_lender.py "
            f"ก่อนเพื่อสร้างไฟล์นี้ (สคริปต์นี้ตั้งใจไม่ re-fetch จาก BOT ซ้ำ "
            f"เพื่อไม่ให้ผลลัพธ์เปลี่ยนถ้า BOT revise ตัวเลขย้อนหลังโดยไม่รู้ตัว)"
        )
    if df.empty:
        raise RuntimeError(f"'{CSV_PATH}' ว่างเปล่า")

    lender_cols = [c for c in df.columns if c not in ("year", "quarter")]
    missing_group = [c for c in lender_cols if c not in GROUP_OF]
    if missing_group:
        raise RuntimeError(
            f"พบ lender column ที่ไม่มีใน GROUP_OF mapping: {missing_group} — "
            f"CSV structure เปลี่ยนไปจากตอนเขียนสคริปต์นี้ ต้องอัปเดต mapping ก่อน"
        )

    df["period"] = df["year"].astype(str) + "Q" + df["quarter"].astype(str)
    df = df.sort_values(["year", "quarter"]).reset_index(drop=True)
    return df


def main():
    df = load_data()
    lender_cols = [c for c in GROUP_OF if c in df.columns]
    # stable order: bank, nonbank, other (same convention as prior chart)
    ordered_cols = (
        [c for c in lender_cols if GROUP_OF[c] == "bank"]
        + [c for c in lender_cols if GROUP_OF[c] == "nonbank"]
        + [c for c in lender_cols if GROUP_OF[c] == "other"]
    )

    print("=" * 76)
    print(f"โหลดข้อมูลจาก {CSV_PATH}: {len(df)} ไตรมาส "
          f"({df['period'].iloc[0]} - {df['period'].iloc[-1]}), "
          f"{len(ordered_cols)} lender types")
    print("=" * 76)

    plot_streamgraph(df, ordered_cols)
    plot_diverging_bar(df, ordered_cols)


# =====================================================================
# Chart 1: Stream graph (ThemeRiver) — matplotlib stackplot(baseline='sym')
# is literally documented as "sometimes called ThemeRiver"
# =====================================================================
def plot_streamgraph(df: pd.DataFrame, ordered_cols: list):
    fig, ax = plt.subplots(figsize=(13, 7.5))
    x = range(len(df))
    ys = [df[c].values for c in ordered_cols]
    colors = [COLOR_OF[c] for c in ordered_cols]

    ax.stackplot(x, ys, labels=ordered_cols, colors=colors, baseline="sym", alpha=0.92)

    n = len(df)
    step = max(1, n // 18)
    ax.set_xticks(list(x)[::step])
    ax.set_xticklabels(df["period"].iloc[::step], rotation=45, ha="right")

    ax.set_yticks([])  # ThemeRiver: absolute Y position is not meaningful, only band width is
    ax.set_xlabel("Quarter")
    ax.set_title(
        "Thailand Household Debt by Lender — Stream Graph (ThemeRiver), 2015Q1–2023Q4\n"
        "Source: Bank of Thailand, EC_MB_039 (reportID=775)  |  Band width = % of GDP "
        "(absolute level) — vertical position carries no meaning (symmetric baseline)\n"
        "Blue = bank group, red/orange = nonbank/near-bank group, grey = other",
        fontsize=10.5, fontweight="bold",
    )
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=3, fontsize=8, frameon=True)
    fig.tight_layout()

    out_path = "thailand_household_debt_streamgraph.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"Stream graph saved to: {out_path}")


# =====================================================================
# Chart 2: Diverging bar chart — QoQ pp change by group, stacked with
# positives above zero and negatives below zero (not simple sequential
# stacking, which would misrepresent sign)
# =====================================================================
def plot_diverging_bar(df: pd.DataFrame, ordered_cols: list):
    group_totals = pd.DataFrame({
        "bank": df[[c for c in ordered_cols if GROUP_OF[c] == "bank"]].sum(axis=1),
        "nonbank": df[[c for c in ordered_cols if GROUP_OF[c] == "nonbank"]].sum(axis=1),
        "other": df[[c for c in ordered_cols if GROUP_OF[c] == "other"]].sum(axis=1),
    })
    qoq_change = group_totals.diff().iloc[1:].reset_index(drop=True)
    periods = df["period"].iloc[1:].reset_index(drop=True)
    total_change = qoq_change.sum(axis=1)

    print()
    print("=" * 76)
    print("QoQ percentage-point change by group (household debt, % of GDP)")
    print("=" * 76)
    print_df = qoq_change.copy()
    print_df.insert(0, "period", periods)
    print_df["total"] = total_change
    with pd.option_context("display.max_rows", None, "display.width", 120):
        print(print_df.round(2).to_string(index=False))

    fig, ax = plt.subplots(figsize=(13, 7.5))
    x = range(len(periods))

    pos_bottom = pd.Series(0.0, index=qoq_change.index)
    neg_bottom = pd.Series(0.0, index=qoq_change.index)
    for grp in ["bank", "nonbank", "other"]:
        vals = qoq_change[grp]
        pos_vals = vals.clip(lower=0)
        neg_vals = vals.clip(upper=0)
        ax.bar(x, pos_vals, bottom=pos_bottom, color=GROUP_COLOR[grp], width=0.75,
               label=GROUP_LABEL[grp], zorder=3)
        ax.bar(x, neg_vals, bottom=neg_bottom, color=GROUP_COLOR[grp], width=0.75, zorder=3)
        pos_bottom += pos_vals
        neg_bottom += neg_vals

    ax.axhline(0, color="#333333", linewidth=1.0, zorder=2)
    ax.plot(x, total_change.values, color="black", linewidth=1.5, linestyle="--",
            marker="o", markersize=3, zorder=4, label="Total QoQ change (all groups)")

    n = len(periods)
    step = max(1, n // 18)
    ax.set_xticks(list(x)[::step])
    ax.set_xticklabels(periods.iloc[::step], rotation=45, ha="right")

    ax.set_ylabel("QoQ Δ (percentage points of GDP)")
    ax.set_xlabel("Quarter")
    ax.yaxis.set_major_locator(MultipleLocator(1))
    ax.set_title(
        "Thailand Household Debt — QoQ Change by Lender Group, 2015Q2–2023Q4\n"
        "Source: Bank of Thailand, EC_MB_039 (reportID=775)  |  Diverging stacked bar: "
        "positive contributions stack above zero, negative below\n"
        "Dashed line = total QoQ change (sum of all 3 groups)",
        fontsize=10.5, fontweight="bold",
    )
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=2, fontsize=8, frameon=True)
    fig.tight_layout()

    out_path = "thailand_household_debt_diverging_bar.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print()
    print(f"Diverging bar chart saved to: {out_path}")


if __name__ == "__main__":
    main()
