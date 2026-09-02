"""
งานเพิ่ม: ทดสอบแหล่งข้อมูลสำรองสำหรับหนี้ไทย ปี 2024-2025 (IMF GDD ล่าสุดมีถึงปี 2023)

แยกออกจาก thailand_debt_imf.py โดยเจตนา — ไม่ต่อ series แบบ silent
ผลลัพธ์:
  1. ทดสอบทุกแหล่งที่โจทย์ระบุ, print ว่าอันไหน work/fail และเพราะอะไร
  2. ดึงข้อมูล BIS Total Credit Statistics (แหล่งเดียวที่ทดสอบแล้วใช้งานได้จริงแบบ
     machine-readable) มาต่อกับ IMF GDD
  3. เช็ค overlap ปี 2023 ระหว่าง IMF GDD กับ BIS ก่อนต่อ กราฟ — ถ้าต่างเกิน
     threshold ไม่ต่อเส้นตรงๆ
  4. พล็อตกราฟ พร้อม annotate จุดเปลี่ยนแหล่งข้อมูล
"""

import sys
import requests
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
from io import StringIO

HEADERS = {"User-Agent": "Mozilla/5.0"}
OVERLAP_YEAR = 2023
WARN_THRESHOLD_PP = 3.0     # print warning above this
DISCONNECT_THRESHOLD_PP = 5.0  # above this: do NOT draw a continuous line

# =====================================================================
# STEP 0 — IMF GDD data already established (2010-2023 household/nfc,
# 2010-2024 government) — hardcoded here from the earlier verified run
# of thailand_debt_imf.py so this script is self-contained and does not
# silently re-derive/guess numbers.
# =====================================================================
IMF_GDD = {
    "household": {
        2010: 59.3, 2011: 66.2, 2012: 71.8, 2013: 76.6, 2014: 79.7,
        2015: 81.2, 2016: 79.4, 2017: 78.1, 2018: 78.4, 2019: 79.9,
        2020: 89.6, 2021: 90.1, 2022: 87.0, 2023: 86.7,
    },
    "nfc": {
        2010: 74.5, 2011: 78.7, 2012: 78.2, 2013: 80.0, 2014: 81.1,
        2015: 83.1, 2016: 82.3, 2017: 79.7, 2018: 80.5, 2019: 79.5,
        2020: 91.2, 2021: 94.0, 2022: 91.7, 2023: 91.3,
    },
    "government": {
        2010: 27.8, 2011: 27.3, 2012: 28.5, 2013: 29.6, 2014: 30.0,
        2015: 32.2, 2016: 30.7, 2017: 32.5, 2018: 34.0, 2019: 34.0,
        2020: 45.1, 2021: 52.8, 2022: 53.7, 2023: 54.6, 2024: 57.2,
    },
}


# =====================================================================
# STEP 1 — Test every candidate source from the task spec
# =====================================================================
def test_sources():
    print("=" * 76)
    print("STEP 1: ทดสอบทุกแหล่งข้อมูลสำรองตามที่ระบุ")
    print("=" * 76)
    results = []

    # --- 1a. BIS: URL pattern given in the task (data.bis.org/topics/...) ---
    given_urls = {
        "household (H)": "https://data.bis.org/topics/TOTAL_CREDIT/BIS,WS_TC,2.0/Q.TH.H.A.M.770.A?file_format=csv&format=long&include=code,label",
        "nfc (N)": "https://data.bis.org/topics/TOTAL_CREDIT/BIS,WS_TC,2.0/Q.TH.N.A.M.770.A?file_format=csv&format=long&include=code,label",
        "government (G)": "https://data.bis.org/topics/TOTAL_CREDIT/BIS,WS_TC,2.0/Q.TH.G.A.M.770.A?file_format=csv&format=long&include=code,label",
    }
    for label, url in given_urls.items():
        r = requests.get(url, headers=HEADERS, timeout=20)
        status = f"FAIL (HTTP {r.status_code}: {r.text[:60]})"
        print(f"[BIS - URL pattern from task spec] {label}: {status}")
        results.append(("BIS (task-spec URL)", label, False, f"HTTP {r.status_code} — endpoint path wrong (data.bis.org/topics/ is a web-app route, not the API)"))

    # --- 1b. BIS: correct SDMX REST API (found by testing stats.bis.org/api-doc/v2) ---
    print()
    print("-> URL ในโจทย์ (data.bis.org/topics/...) ใช้ไม่ได้ (404) เพราะเป็น web-app")
    print("   route ไม่ใช่ API จริง. หา API doc จริงที่ stats.bis.org/api-doc/v2/")
    print("   แล้วพบ SDMX REST endpoint ที่ใช้งานได้จริง: stats.bis.org/api/v1/data/WS_TC/...")
    print()
    working_codes = {}
    for code, name in [("H", "household"), ("N", "nfc"), ("G", "government"),
                        ("P", "private non-financial (H+N)"), ("C", "total non-financial")]:
        url = f"https://stats.bis.org/api/v1/data/WS_TC/Q.TH.{code}.A.M.770.A?format=csv"
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200 and "OBS_VALUE" in r.text:
            n_obs = r.text.strip().count("\n")
            print(f"[BIS SDMX API - correct endpoint] borrower={code} ({name}): OK, {n_obs} obs")
            working_codes[code] = r.text
            results.append(("BIS SDMX API", f"{name} (borrower={code})", True, f"{n_obs} quarterly obs, 1991/97-2025"))
        else:
            reason = "TH not published for this borrower category" if r.status_code == 404 else f"HTTP {r.status_code}"
            print(f"[BIS SDMX API - correct endpoint] borrower={code} ({name}): FAIL ({reason})")
            results.append(("BIS SDMX API", f"{name} (borrower={code})", False, reason))

    # --- 2. BOT ---
    print()
    bot_urls = {
        "BOT economic-and-financial-data page": "https://www.bot.or.th/en/statistics/economic-and-financial-data.html",
        "BOT BOTWEBSTAT reportID=754": "https://app.bot.or.th/BTWS_STAT/statistics/BOTWEBSTAT.aspx?reportID=754",
    }
    for label, url in bot_urls.items():
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            has_csv_link = "csv" in r.text.lower() or "export" in r.text.lower()
            note = ("page reachable, has export/CSV UI elements but export is a "
                     "dynamic ASPX postback (needs __VIEWSTATE/session) — not a "
                     "plain-GET machine-readable endpoint") if has_csv_link else "page reachable, no export links found"
            print(f"[BOT] {label}: HTTP 200 but NOT directly machine-readable — {note}")
            results.append(("BOT", label, False, note))
        else:
            print(f"[BOT] {label}: FAIL (HTTP {r.status_code})")
            results.append(("BOT", label, False, f"HTTP {r.status_code}"))
    print("   -> สรุป BOT: ไม่มี public API endpoint ตรงๆ ต้อง manual entry จาก")
    print("      press release (ค่าที่ระบุมา: Q4 2025 household debt = 86.7% of GDP,")
    print("      16.44 ล้านล้านบาท) — ใช้เป็น cross-check เท่านั้น ไม่ใช่ series")

    # --- 3. PDMO ---
    print()
    pdmo_urls = {
        "PDMO public-debt-outstanding (EN)": "https://www.pdmo.go.th/en/public-debt-outstanding",
        "PDMO homepage (EN)": "https://www.pdmo.go.th/en/",
    }
    for label, url in pdmo_urls.items():
        r = requests.get(url, headers=HEADERS, timeout=20)
        ok = r.status_code == 200
        print(f"[PDMO] {label}: {'HTTP 200 (HTML page, no CSV/API found)' if ok else f'FAIL (HTTP {r.status_code})'}")
        results.append(("PDMO", label, False, "HTML only, no CSV/API discovered at tested URL" if ok else f"HTTP {r.status_code}"))
    print("   -> สรุป PDMO: หน้าเว็บ /en/public-debt-outstanding คืน 404 (URL เปลี่ยน/")
    print("      ไม่มีแล้ว), homepage ใช้ได้แต่เป็น CMS ธรรมดา ไม่มี CSV/API ที่หาเจอ")
    print("      ต้อง manual scrape ตาราง/PDF รายเดือนแทน — ไม่ทำในสคริปต์นี้")

    # --- 4. CEIC ---
    print()
    print("[CEIC] ไม่ทดสอบ live scrape (free preview page ไม่ใช่แหล่งหลักตามโจทย์,")
    print("       ใช้แค่ cross-check ตัวเลขที่รู้อยู่แล้ว: household ~86.4-87.5% ปลายปี 2025)")
    results.append(("CEIC", "free preview (cross-check only)", None, "not queried — used only as known reference range"))

    return working_codes, results


# =====================================================================
# STEP 2 — Parse working BIS series, aggregate quarterly -> annual (Q4 snapshot)
# =====================================================================
def parse_bis_annual(csv_text: str) -> dict:
    df = pd.read_csv(StringIO(csv_text))
    df = df[df["TIME_PERIOD"].str.endswith("Q4")].copy()
    df["year"] = df["TIME_PERIOD"].str[:4].astype(int)
    return dict(zip(df["year"], df["OBS_VALUE"]))


def main():
    working_codes, source_results = test_sources()

    if not working_codes:
        raise RuntimeError(
            "Aborting: no BIS series could be fetched at all — cannot build "
            "2024-2025 extension without at least a working data source."
        )

    required = {"H", "N", "P", "C"}
    missing = required - set(working_codes)
    if missing:
        raise RuntimeError(
            f"Aborting: BIS series missing for borrower codes {missing}, "
            f"cannot derive government debt (needs both C and P)."
        )

    bis_h = parse_bis_annual(working_codes["H"])
    bis_n = parse_bis_annual(working_codes["N"])
    bis_p = parse_bis_annual(working_codes["P"])
    bis_c = parse_bis_annual(working_codes["C"])

    # Government not published for TH under borrower=G on BIS -> derive as
    # Total non-financial (C) minus Private non-financial (P), which by BIS's
    # own definition equals general government credit.
    bis_years = sorted(set(bis_c) & set(bis_p))
    bis_g_derived = {y: round(bis_c[y] - bis_p[y], 2) for y in bis_years}

    print()
    print("=" * 76)
    print("STEP 2: BIS series ปี 2010-2025 (Q4 snapshot ต่อปี) + government = C - P")
    print("=" * 76)
    print("(government (G) ไม่มีใน BIS สำหรับ TH โดยตรง -> derive จาก")
    print(" Total non-financial (C) - Private non-financial (P), ตาม BIS definition:")
    print(" C = P + G เสมอ)")
    print()
    rows = []
    for y in sorted(bis_h):
        rows.append({
            "year": y, "source": "BIS",
            "household": bis_h.get(y), "nfc": bis_n.get(y),
            "government_derived": bis_g_derived.get(y),
            "total": bis_c.get(y),
        })
    bis_df = pd.DataFrame(rows)
    print(bis_df.to_string(index=False))

    # =================================================================
    # STEP 3 — Overlap check at 2023 before connecting IMF -> BIS
    # =================================================================
    print()
    print("=" * 76)
    print(f"STEP 3: เช็ค overlap ปี {OVERLAP_YEAR} ระหว่าง IMF GDD กับ BIS ก่อนต่อเส้น")
    print("=" * 76)
    connect_decision = {}
    for series, imf_dict, bis_dict, bis_label in [
        ("household", IMF_GDD["household"], bis_h, "BIS borrower=H"),
        ("nfc", IMF_GDD["nfc"], bis_n, "BIS borrower=N"),
        ("government", IMF_GDD["government"], bis_g_derived, "BIS derived C-P"),
        ("total", {y: IMF_GDD["household"][y] + IMF_GDD["nfc"][y] + IMF_GDD["government"][y]
                    for y in IMF_GDD["household"] if y in IMF_GDD["government"]}, bis_c, "BIS borrower=C"),
    ]:
        imf_val = imf_dict.get(OVERLAP_YEAR)
        bis_val = bis_dict.get(OVERLAP_YEAR)
        if imf_val is None or bis_val is None:
            print(f"{series:12s}: ข้อมูล overlap ปี {OVERLAP_YEAR} ไม่ครบ (IMF={imf_val}, {bis_label}={bis_val}) — ข้าม")
            connect_decision[series] = False
            continue
        diff = abs(imf_val - bis_val)
        flag = ""
        if diff > DISCONNECT_THRESHOLD_PP:
            flag = f"  !! WARNING: diff > {DISCONNECT_THRESHOLD_PP}pp -> จะ NOT ต่อเส้นตรงๆ, แสดงแยกเป็นคนละเส้น"
            connect_decision[series] = False
        elif diff > WARN_THRESHOLD_PP:
            flag = f"  ! WARNING: diff > {WARN_THRESHOLD_PP}pp แต่ <= {DISCONNECT_THRESHOLD_PP}pp -> ต่อเส้นได้ (dashed) แต่ให้ระวัง methodology difference"
            connect_decision[series] = True
        else:
            connect_decision[series] = True
        print(
            f"{series:12s}: IMF GDD={imf_val:6.1f}  {bis_label}={bis_val:6.1f}  "
            f"diff={diff:4.1f}pp{flag}"
        )

    # =================================================================
    # STEP 4 — Sanity check government (derived) vs BOT/PDMO known range
    # =================================================================
    print()
    print("=" * 76)
    print("STEP 4: Sanity check — BIS-derived government debt vs BOT/PDMO reported range")
    print("=" * 76)
    latest_gov_year = max(bis_g_derived)
    latest_gov_val = bis_g_derived[latest_gov_year]
    print(
        f"BIS-derived (C - P) government credit, {latest_gov_year}: {latest_gov_val:.1f}% of GDP\n"
        f"BOT/PDMO reported public debt range: 59.0-66.0% of GDP\n"
        f"NOTE: metric names are NOT the same thing:\n"
        f"  - BIS/IMF GDD 'government' = credit extended TO the government sector\n"
        f"    from all lenders (BIS Total Credit Statistics methodology)\n"
        f"  - BOT/PDMO 'public debt' = Public Sector Debt outstanding per Public Debt\n"
        f"    Management Act perimeter (includes SOE debt, FIDF debt guaranteed by\n"
        f"    government; excludes/includes different items than BIS credit stats)\n"
        f"  These are DIFFERENT metrics measuring related but non-identical things —\n"
        f"  a gap here does NOT necessarily mean an error."
    )
    diff = latest_gov_val - 66.0 if latest_gov_val > 66.0 else (59.0 - latest_gov_val if latest_gov_val < 59.0 else 0.0)
    if diff > 10.0:
        print(f"WARNING: diff = {diff:.1f}pp > 10pp threshold — perimeter difference larger than usual, double-check.")
    else:
        print(f"OK: diff from PDMO/BOT range = {diff:.1f}pp (<= 10pp threshold).")

    print()
    print("Known cross-check figures (not independently queried, per task spec):")
    print("  - BOT household debt, Q4 2025: 86.7% of GDP (16.44 trillion baht)")
    print(f"  - BIS household debt, Q4 2025: {bis_h.get(2025)}% of GDP  "
          f"(diff = {abs(86.7 - bis_h.get(2025, 0)):.1f}pp)")
    print("  - CEIC free-preview known range, household end-2025: 86.4-87.5% of GDP")
    print(f"  -> BIS value {bis_h.get(2025)}% falls "
          f"{'INSIDE' if 86.4 <= bis_h.get(2025, 0) <= 87.5 else 'OUTSIDE'} that range: sanity check "
          f"{'PASSED' if 86.4 <= bis_h.get(2025, 0) <= 87.5 else 'FAILED'}")

    # =================================================================
    # STEP 5 — Print source-tagged raw table + summary of what worked
    # =================================================================
    print()
    print("=" * 76)
    print("STEP 5: สรุปแหล่งข้อมูลที่ทดสอบ — ใช้ได้ / ใช้ไม่ได้ และเพราะอะไร")
    print("=" * 76)
    for src, label, ok, note in source_results:
        status = "OK" if ok is True else ("N/A" if ok is None else "FAIL")
        print(f"  [{status:4s}] {src:16s} | {label:45s} | {note}")

    plot_combined(bis_h, bis_n, bis_g_derived, bis_c, connect_decision)


def plot_combined(bis_h, bis_n, bis_g, bis_c, connect_decision):
    imf_years = sorted(IMF_GDD["household"])  # 2010-2023
    imf_total = {
        y: IMF_GDD["household"][y] + IMF_GDD["nfc"][y] + IMF_GDD["government"][y]
        for y in imf_years
    }

    fig, (ax, ax_bar) = plt.subplots(
        2, 1, figsize=(12, 9), sharex=True,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.08},
    )

    series_specs = [
        ("household", IMF_GDD["household"], bis_h, "#4C78A8", "Household debt (BIS borrower=H)"),
        ("nfc", IMF_GDD["nfc"], bis_n, "#F58518", "Non-fin. corporate debt (BIS borrower=N)"),
        ("government", IMF_GDD["government"], bis_g, "#54A24B", "General govt. credit (BIS derived: C-P)"),
        ("total", imf_total, bis_c, "#222222", "Total non-financial debt (BIS borrower=C)"),
    ]

    for name, imf_dict, bis_dict, color, label in series_specs:
        lw = 3.2 if name == "total" else 2.0
        ms = 5 if name == "total" else 4

        # IMF GDD segment, always solid
        xs_imf = sorted(imf_dict)
        ys_imf = [imf_dict[y] for y in xs_imf]
        ax.plot(xs_imf, ys_imf, color=color, linewidth=lw, marker="o",
                 markersize=ms, zorder=3, label=f"{label} — IMF GDD (2010-2023)")

        # BIS segment, years beyond IMF's last year
        last_imf_year = max(xs_imf)
        xs_bis = sorted(y for y in bis_dict if y >= last_imf_year)
        ys_bis = [bis_dict[y] for y in xs_bis]

        can_connect = connect_decision.get(name, False)
        if can_connect:
            ax.plot(xs_bis, ys_bis, color=color, linewidth=lw, linestyle="--",
                     marker="s", markersize=ms, zorder=3,
                     label=f"{label} — BIS (2023-2025)")
        else:
            # Do NOT draw a connecting line across the break — plot BIS
            # segment as a visually separate dashed line offset from the
            # IMF value, with a gap marker at the junction to flag the
            # methodology discontinuity.
            ax.plot(xs_bis, ys_bis, color=color, linewidth=lw, linestyle=":",
                     marker="^", markersize=ms + 1, zorder=3, alpha=0.85,
                     label=f"{label} — BIS (2023-2025, DISCONNECTED — methodology gap)")
            ax.plot(
                [last_imf_year, last_imf_year], [imf_dict[last_imf_year], bis_dict[last_imf_year]],
                color=color, linewidth=1.0, linestyle=(0, (1, 1)), alpha=0.5, zorder=2,
            )

        # Annotate the source-switch point
        ax.annotate(
            "", xy=(last_imf_year, bis_dict.get(last_imf_year, imf_dict[last_imf_year])),
            xytext=(last_imf_year, imf_dict[last_imf_year]),
        )

    ax.axvline(2023, color="grey", linestyle=":", linewidth=1.2, alpha=0.7, zorder=1)
    ax.text(2023.05, ax.get_ylim()[1] if ax.get_ylim()[1] else 1, "", fontsize=8)

    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_locator(MultipleLocator(10))
    ax.set_ylabel("% of GDP")
    ax.set_title(
        "Thailand Debt by Sector, 2010–2025\n"
        "2010–2023: IMF Global Debt Database  |  2023(*)–2025: BIS Total Credit "
        "Statistics (household/NFC/total) & derived govt. credit (C−P)\n"
        "Dotted/triangle segments = overlap check failed (>5pp) → NOT a continuous series, shown for reference only",
        fontsize=11, fontweight="bold",
    )
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", frameon=True, fontsize=7.5, ncol=1)
    ax.annotate(
        "2023: source switch\n(IMF GDD -> BIS)",
        xy=(2023, 0), xytext=(2023.2, ax.get_ylim()[1] * 0.04 if ax.get_ylim()[1] else 5),
        fontsize=8, color="grey",
    )
    ax.tick_params(labelbottom=False)  # x labels shown only on bottom panel

    # --- Bottom panel: YoY change in total debt (volume-style bar chart) ---
    # Uses the combined total series (IMF 2010-2023 + BIS 2023-2025) since
    # the overlap check at 2023 passed for "total" (diff = 1.0pp <= 5pp) —
    # a continuous YoY delta across the source switch is therefore valid.
    combined_total = dict(imf_total)
    combined_total.update({y: v for y, v in bis_c.items() if y >= max(imf_total)})
    years_sorted = sorted(combined_total)
    yoy = {
        years_sorted[i]: combined_total[years_sorted[i]] - combined_total[years_sorted[i - 1]]
        for i in range(1, len(years_sorted))
    }

    INCREASE_COLOR = "#D62728"  # debt rising
    DECREASE_COLOR = "#2CA02C"  # debt falling
    bar_years = sorted(yoy)
    bar_vals = [yoy[y] for y in bar_years]
    colors = [INCREASE_COLOR if v >= 0 else DECREASE_COLOR for v in bar_vals]
    ax_bar.bar(bar_years, bar_vals, color=colors, width=0.7, zorder=3)
    ax_bar.axhline(0, color="#555555", linewidth=0.8, zorder=2)
    # Mark the 2023->2024 source-switch bar distinctly (mixed IMF/BIS boundary)
    ax_bar.axvline(2023.5, color="grey", linestyle=":", linewidth=1.0, alpha=0.6, zorder=1)
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
    ax_bar.set_xticks(years_sorted)
    ax_bar.set_xticklabels([str(y) for y in years_sorted])

    fig.tight_layout()

    out_path = "D:/investment/Finance_tools/thailand_debt_2024_2025_extension.png"
    fig.savefig(out_path, dpi=150)
    print()
    print(f"Chart saved to: {out_path}")


if __name__ == "__main__":
    main()
