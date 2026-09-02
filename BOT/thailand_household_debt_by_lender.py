"""
Task ใหม่ (แยกจาก pipeline เดิม — IMF GDD 3-sector debt-to-GDP):
Household debt breakdown by lender type, จาก BOT table EC_MB_039 (reportID=775)

ผลลัพธ์เป็นกราฟที่ 2 แยกต่างหาก — ไม่รวมเส้นกับกราฟ sector (household/NFC/government)
เดิม เพราะคนละมิติ: breakdown-within-household-sector vs sector-level totals

หมายเหตุสำคัญที่พบระหว่างดึงข้อมูล (อ่านก่อนใช้ผลลัพธ์):
  BOT report นี้ (EC_MB_039) ณ วันที่ดึง (last update บนหน้าเว็บ = 5 ธ.ค. 2567)
  มีข้อมูลถึงแค่ Q4/2566 (Q4 2023) เท่านั้น — ปุ่ม drpToYear บนฟอร์มเองก็ไม่มี
  ตัวเลือกปี 2567/2568 ให้เลือก และถ้าพยายาม POST ปีที่ไม่อยู่ใน dropdown
  (เช่น "2025xxxx") server จะ reject ด้วย EVENTVALIDATION error (custom error
  page "Please consult with your administrator") ไม่ใช่ 404 — เพราะ ASP.NET
  WebForms validate ค่าที่ POST กลับมาว่าต้องอยู่ใน <select> ตัวเลือกเดิมที่เคย
  ส่งไปใน initial GET เท่านั้น ดังนั้น**ไม่สามารถดึงปี 2024-2025 จาก endpoint
  นี้ได้จริง** ต่างจากที่ตั้งใจไว้ตอนแรก (2015-2025) — สคริปต์นี้จึงได้แค่
  2015-2023 (Q1/2558 - Q4/2566)
"""

import sys
import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
from bs4 import BeautifulSoup
from io import StringIO

HEADERS = {"User-Agent": "Mozilla/5.0"}
REPORT_URL = "https://app.bot.or.th/BTWS_STAT/statistics/BOTWEBSTAT.aspx?reportID=775"

REQUESTED_FROM_YEAR_AD = 2015
REQUESTED_TO_YEAR_AD = 2025   # what the task asked for
# what the BOT form's own dropdown actually allows as of fetch time — filled
# in at runtime after inspecting the GET response, never hardcoded/assumed

OVERLAP_WARN_THRESHOLD_PP = 3.0

# IMF GDD household debt-to-GDP, Thailand — hardcoded from the already-verified
# thailand_debt_imf.py run (self-contained per project convention: don't
# re-hit the IMF API from this unrelated script)
IMF_HH_LS = {
    2015: 81.2, 2016: 79.4, 2017: 78.1, 2018: 78.4, 2019: 79.9,
    2020: 89.6, 2021: 90.1, 2022: 87.0, 2023: 86.7,
}

# Row layout of the BOT EC_MB_039 table (1-indexed row numbers as printed in
# the table's own first column) -> (english label, group)
# group: "bank", "nonbank", "other", or "subtotal" (subtotal rows excluded
# from the stack to avoid double-counting)
ROW_MAP = {
    1: ("Deposit-taking institutions (subtotal)", "subtotal"),
    2: ("Commercial banks", "bank"),
    3: ("Specialized state banks", "bank"),
    4: ("Savings cooperatives", "nonbank"),
    5: ("Other deposit-taking institutions", "other"),
    6: ("Other financial institutions (subtotal)", "subtotal"),
    7: ("Credit card / leasing / personal loan cos.", "nonbank"),
    8: ("Insurance companies", "other"),
    9: ("Securities companies", "other"),
    10: ("Asset management companies", "other"),
    11: ("Pawnshops", "nonbank"),
    12: ("Others", "other"),
    13: ("Total", "total"),
}


def fetch_bot_table():
    """Perform the ASP.NET __doPostBack dance: GET the form, extract
    __VIEWSTATE/__VIEWSTATEGENERATOR/__EVENTVALIDATION, then POST with the
    desired date range selected. Raises RuntimeError with a clear reason on
    any failure — never silently returns partial/empty data.
    """
    s = requests.Session()

    r1 = s.get(REPORT_URL, headers=HEADERS, timeout=30)
    if r1.status_code != 200:
        raise RuntimeError(f"BOT reportID=775 initial GET failed: HTTP {r1.status_code}")
    soup = BeautifulSoup(r1.text, "html.parser")

    def field(id_):
        el = soup.find(id=id_)
        if el is None:
            raise RuntimeError(f"BOT form field '{id_}' not found in initial GET response — page structure changed")
        return el.get("value", "")

    # Discover what year range the form's own dropdown actually offers —
    # never assume 2015-2025 is selectable
    to_year_select = soup.find(id="drpToYear")
    if to_year_select is None:
        raise RuntimeError("drpToYear dropdown not found — cannot determine available year range")
    # NOTE: the <option value="2003xxxx">2546</option> convention on this form
    # uses the AD year as the VALUE and the BE (Buddhist) year only as the
    # visible LABEL — value is already AD, no +/-543 conversion needed here.
    available_years_option_values = [
        opt.get("value") for opt in to_year_select.find_all("option") if opt.get("value")
    ]
    available_years_ad = sorted(int(v[:4]) for v in available_years_option_values)
    max_available_ad = max(available_years_ad)
    min_available_ad = min(available_years_ad)

    print(f"BOT form's own drpToYear dropdown offers years: {min_available_ad}-{max_available_ad} (AD)")
    if max_available_ad < REQUESTED_TO_YEAR_AD:
        print(
            f"WARNING: requested data through {REQUESTED_TO_YEAR_AD}, but BOT's form only "
            f"allows selecting up to {max_available_ad}. Will fetch {REQUESTED_FROM_YEAR_AD}-"
            f"{max_available_ad} instead — data for {max_available_ad + 1}-{REQUESTED_TO_YEAR_AD} "
            f"is NOT available from this BOT report as of the fetch date."
        )

    from_year_ad = max(REQUESTED_FROM_YEAR_AD, min_available_ad)
    to_year_ad = min(REQUESTED_TO_YEAR_AD, max_available_ad)

    post_data = {
        "__EVENTTARGET": "",
        "__EVENTARGUMENT": "",
        "__LASTFOCUS": "",
        "__VIEWSTATE": field("__VIEWSTATE"),
        "__VIEWSTATEGENERATOR": field("__VIEWSTATEGENERATOR"),
        "__EVENTVALIDATION": field("__EVENTVALIDATION"),
        "drpPeriod": "QTR",
        "drpFromQuarter": "xxxx03xx",
        "drpFromYear": f"{from_year_ad}xxxx",
        "drpToQuarter": "xxxx12xx",
        "drpToYear": f"{to_year_ad}xxxx",
        "btnSubmit": "Submit",
    }

    r2 = s.post(REPORT_URL, data=post_data, headers=HEADERS, timeout=30)
    if r2.status_code != 200:
        raise RuntimeError(f"BOT reportID=775 POST failed: HTTP {r2.status_code}")
    if "Please consult with your administrator" in r2.text or "CustomErrorPage" in r2.text:
        raise RuntimeError(
            f"BOT reportID=775 POST rejected the year range {from_year_ad}-{to_year_ad} "
            f"(server returned its generic ASP.NET error page — likely an "
            f"EVENTVALIDATION mismatch, meaning the posted year value wasn't "
            f"among the options actually offered by the form)."
        )

    tables = pd.read_html(StringIO(r2.text))
    if not tables or tables[0].shape[0] < 13:
        raise RuntimeError(
            f"BOT reportID=775 POST succeeded but the data table looks wrong "
            f"(got {len(tables)} tables, first shape "
            f"{tables[0].shape if tables else None}) — page structure may have changed"
        )

    return tables[0], from_year_ad, to_year_ad


def parse_table(raw: pd.DataFrame) -> pd.DataFrame:
    raw = raw.copy()
    raw.columns = ["row_num", "label_th"] + list(raw.columns[2:])
    quarter_cols = list(raw.columns[2:])

    records = []
    for _, row in raw.iterrows():
        row_num = int(row["row_num"])
        if row_num not in ROW_MAP or ROW_MAP[row_num][1] in ("subtotal", "total"):
            continue
        label_en, group = ROW_MAP[row_num]
        for col in quarter_cols:
            # column header format: "Q4/2566 p" or "Q3/2566 r" -> strip flag
            qtr_str = str(col).split()[0]  # "Q4/2566"
            q, be_year = qtr_str.split("/")
            year_ad = int(be_year) - 543
            quarter = int(q.replace("Q", ""))
            val = row[col]
            records.append({
                "year": year_ad, "quarter": quarter, "row_num": row_num,
                "lender_type": label_en, "group": group,
                "value_thb_mn": float(val) if pd.notna(val) else np.nan,
            })

    return pd.DataFrame(records)


def main():
    print("=" * 76)
    print("STEP 1: ดึงข้อมูล BOT EC_MB_039 (reportID=775) ผ่าน ASP.NET postback")
    print("=" * 76)
    raw_table, from_year_ad, to_year_ad = fetch_bot_table()
    print(f"OK: ดึงข้อมูลสำเร็จ ช่วง {from_year_ad}-{to_year_ad} (AD), "
          f"{raw_table.shape[1] - 2} ไตรมาส, {raw_table.shape[0]} แถว")

    long_df = parse_table(raw_table)
    if long_df.empty:
        raise RuntimeError("Parsed table is empty — row/column mapping likely broken")

    # total row, for GDP-denominator derivation and sanity checks
    total_raw = raw_table[raw_table.iloc[:, 0] == 13].iloc[0]
    ratio_raw = raw_table[raw_table.iloc[:, 0] == 14].iloc[0]  # official BOT %-of-GDP row
    quarter_cols = list(raw_table.columns[2:])

    gdp_implied = {}
    total_by_q = {}
    ratio_by_q = {}
    for col in quarter_cols:
        qtr_str = str(col).split()[0]
        q, be_year = qtr_str.split("/")
        year_ad, quarter = int(be_year) - 543, int(q.replace("Q", ""))
        total_val = float(total_raw[col])
        ratio_val = float(ratio_raw[col])
        total_by_q[(year_ad, quarter)] = total_val
        ratio_by_q[(year_ad, quarter)] = ratio_val
        # BOT's own ratio = total / rolling-4Q-GDP * 100  =>  implied GDP:
        gdp_implied[(year_ad, quarter)] = total_val / (ratio_val / 100.0)

    long_df["gdp_implied_thb_mn"] = long_df.apply(
        lambda r: gdp_implied[(r["year"], r["quarter"])], axis=1
    )
    long_df["pct_of_gdp"] = long_df["value_thb_mn"] / long_df["gdp_implied_thb_mn"] * 100.0

    # =================================================================
    # STEP 2 — raw table print (THB mn), sorted by lender then time
    # =================================================================
    print()
    print("=" * 76)
    print("STEP 2: Raw data — household debt by lender type (THB million), by quarter")
    print("=" * 76)
    pivot_raw = long_df.pivot_table(
        index=["year", "quarter"], columns="lender_type", values="value_thb_mn"
    ).sort_index()
    with pd.option_context("display.max_rows", None, "display.width", 200, "display.max_columns", None):
        print(pivot_raw.round(0).to_string())

    # =================================================================
    # STEP 3 — % of GDP table (own denominator, consistent w/ BOT footnote 9/10)
    # =================================================================
    print()
    print("=" * 76)
    print("STEP 3: % of GDP by lender type (denominator = implied rolling-4Q GDP")
    print("        back-derived from BOT's own total-credit-to-GDP ratio, row 14)")
    print("=" * 76)
    pivot_pct = long_df.pivot_table(
        index=["year", "quarter"], columns="lender_type", values="pct_of_gdp"
    ).sort_index()
    with pd.option_context("display.max_rows", None, "display.width", 200, "display.max_columns", None):
        print(pivot_pct.round(2).to_string())

    # =================================================================
    # STEP 4 — Sanity check: sum(lender types) vs BOT official ratio vs IMF HH_LS
    # =================================================================
    print()
    print("=" * 76)
    print("STEP 4: Sanity check — sum of lender-type %GDP vs BOT official ratio,")
    print("        and BOT Q4 total vs IMF GDD household debt (annual, HH_LS)")
    print("=" * 76)

    sum_check = pivot_pct.sum(axis=1)
    ratio_series = pd.Series(ratio_by_q)
    ratio_series.index = pd.MultiIndex.from_tuples(ratio_series.index, names=sum_check.index.names)
    max_construction_error = (sum_check - ratio_series).abs().max()
    print(
        f"Internal check: sum of all lender-type %GDP vs BOT's own official ratio "
        f"(row 14) — max abs diff across all quarters = {max_construction_error:.4f}pp "
        f"(should be ~0 by construction, since both use the same total/denominator)"
    )

    print()
    print(f"{'Year':6s} {'BOT Q4 total (%GDP)':22s} {'IMF HH_LS (annual)':20s} {'diff (pp)':10s}")
    comparison_rows = []
    for year in sorted(IMF_HH_LS):
        if (year, 4) not in ratio_by_q:
            print(f"{year:<6d} n/a (no Q4 data fetched)")
            continue
        bot_val = ratio_by_q[(year, 4)]
        imf_val = IMF_HH_LS[year]
        diff = bot_val - imf_val
        flag = ""
        if abs(diff) > OVERLAP_WARN_THRESHOLD_PP:
            flag = (
                f"  !! WARNING: diff > {OVERLAP_WARN_THRESHOLD_PP}pp — possible causes: "
                f"BOT coverage change (2023 onward BOT's 'others' row started including "
                f"กยศ./การเคหะแห่งชาติ/pico finance/non-saving cooperatives, widening "
                f"BOT's total vs IMF's), or IMF/BIS classification differences"
            )
        print(f"{year:<6d} {bot_val:<22.1f} {imf_val:<20.1f} {diff:+.1f}{flag}")
        comparison_rows.append((year, bot_val, imf_val, diff))

    max_diff = max(abs(d) for _, _, _, d in comparison_rows)
    if max_diff <= OVERLAP_WARN_THRESHOLD_PP:
        print(
            f"\nOK: all years within {OVERLAP_WARN_THRESHOLD_PP}pp of IMF GDD household debt "
            f"— BOT's own ratio and IMF's HH_LS series track each other closely across "
            f"2015-2023 (both ultimately trace back to BOT/BIS as the primary source)."
        )
    else:
        print(f"\nMax diff observed: {max_diff:.1f}pp (see WARNING rows above)")

    # =================================================================
    # STEP 5 — plot (separate figure — never merged with the sector chart)
    # =================================================================
    plot_stacked(long_df, pivot_pct)

    print()
    print("=" * 76)
    print("SUMMARY")
    print("=" * 76)
    print(f"- ดึงข้อมูลได้จริง: {from_year_ad}-{to_year_ad} เท่านั้น (ไม่ใช่ 2015-2025 ตามที่ขอ")
    print(f"  ในตอนแรก) เพราะ BOT reportID=775 ไม่มีข้อมูลเกิน Q4/2566 ณ วันที่ดึง —")
    print(f"  ดู docstring ต้นไฟล์สำหรับรายละเอียด root cause")
    print(f"- 10 lender-type series + total, converted to %GDP ด้วย denominator เดียวกับ")
    print(f"  ที่ BOT ใช้เอง (row 14 ratio) — ยืนยันด้วย internal check ว่า sum ตรงกับ")
    print(f"  official ratio แทบสมบูรณ์ (max diff {max_construction_error:.4f}pp)")
    print(f"- BOT total vs IMF HH_LS: max diff {max_diff:.1f}pp ตลอด 2015-2023 "
          f"({'ไม่มี' if max_diff <= OVERLAP_WARN_THRESHOLD_PP else 'มี'} warning)")


def plot_stacked(long_df: pd.DataFrame, pivot_pct: pd.DataFrame):
    # composition = % of TOTAL HOUSEHOLD DEBT (not % of GDP) for the main chart
    comp = pivot_pct.div(pivot_pct.sum(axis=1), axis=0) * 100.0
    comp.index = [f"{y}Q{q}" for y, q in comp.index]

    # order: bank group, then nonbank/near-bank group, then other — so the
    # nonbank block sits visually contiguous and its growth is easy to trace
    group_of = {label: grp for _, (label, grp) in ROW_MAP.items() if grp not in ("subtotal", "total")}
    bank_cols = [c for c in comp.columns if group_of.get(c) == "bank"]
    nonbank_cols = [c for c in comp.columns if group_of.get(c) == "nonbank"]
    other_cols = [c for c in comp.columns if group_of.get(c) == "other"]
    ordered_cols = bank_cols + nonbank_cols + other_cols
    comp = comp[ordered_cols]

    bank_colors = ["#1f4e8c", "#5b8fd4"]  # Commercial banks, Specialized state banks
    nonbank_colors = ["#c0392b", "#e67e22", "#f1a208"]  # Savings coop, Credit card/leasing/personal, Pawnshops
    other_colors = ["#95a5a6", "#7f8c8d", "#bdc3c7", "#aab7b8", "#d5dbdb"]

    color_map = {}
    for cols, palette in [(bank_cols, bank_colors), (nonbank_cols, nonbank_colors), (other_cols, other_colors)]:
        for c, col in zip(cols, palette):
            color_map[c] = col
    colors = [color_map[c] for c in comp.columns]

    fig, ax = plt.subplots(figsize=(13, 8))
    x = range(len(comp.index))
    ax.stackplot(x, [comp[c].values for c in comp.columns], labels=comp.columns, colors=colors, alpha=0.9)

    # Highlight overlay: bank-group cumulative share and nonbank/near-bank
    # cumulative share, as bold lines on top of the stack, to directly answer
    # "is nonbank/near-bank growing its share?"
    bank_share = comp[bank_cols].sum(axis=1)
    nonbank_share = comp[nonbank_cols].sum(axis=1)
    ax.plot(x, bank_share.values, color="#0b2545", linewidth=3.0,
             linestyle="-", marker="", zorder=5, label="Bank group total share (cumulative)")
    ax.plot(x, (bank_share + nonbank_share).values, color="#7a1f10", linewidth=3.0,
             linestyle="--", zorder=5, label="Bank + nonbank/near-bank cumulative share")

    n = len(comp.index)
    step = max(1, n // 18)
    ax.set_xticks(list(x)[::step])
    ax.set_xticklabels([comp.index[i] for i in x][::step], rotation=45, ha="right")

    ax.set_ylim(0, 100)
    ax.yaxis.set_major_locator(MultipleLocator(10))
    ax.set_ylabel("% of total household debt (composition)")
    ax.set_xlabel("Quarter")
    ax.set_title(
        "Thailand Household Debt — Composition by Lender Type, 2015Q1–2023Q4\n"
        "Source: Bank of Thailand, EC_MB_039 (reportID=775)  |  100% stacked area — "
        "shows composition shift, NOT level\n"
        "Blue shades = bank group, red/orange shades = nonbank/near-bank group "
        "(savings coop + credit card/leasing/personal loan + pawnshops), grey shades = other",
        fontsize=10.5, fontweight="bold",
    )
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=3, fontsize=8, frameon=True)
    fig.tight_layout()

    out_path = "D:/investment/Finance_tools/thailand_household_debt_lender_breakdown.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print()
    print(f"Chart saved to: {out_path}")

    # also persist the absolute %-of-GDP data for later reuse, per task spec
    csv_path = "D:/investment/Finance_tools/thailand_household_debt_by_lender_pct_gdp.csv"
    pivot_pct.to_csv(csv_path)
    print(f"Absolute %-of-GDP data (for future reuse) saved to: {csv_path}")


if __name__ == "__main__":
    main()
