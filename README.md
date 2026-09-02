# Finance_tools

โฟลเดอร์ reserved สำหรับ **เครื่องมือการเงินทั่วไป** ที่ใช้ข้ามโปรเจกต์
(เช่น data fetcher, ตัวคำนวณ, helper ที่ใช้ร่วมกันระหว่างก้อน 1 / ก้อน 2)

ดูดัชนีรวมที่ [`../README.md`](../README.md)

---

## Thailand Debt-by-Sector Analysis

เครื่องมือดึง + วิเคราะห์ time series หนี้ 3 sector ของไทย (household, non-financial
corporate, government) เป็น % of GDP จากหลายแหล่งข้อมูล

### โครงสร้างไฟล์

| ไฟล์ | เนื้อหา |
|---|---|
| `IMF_only/thailand_debt_imf.py` | ดึงข้อมูลจาก **IMF Global Debt Database (GDD)** ผ่าน DataMapper API เท่านั้น — ปี 2010 ถึงล่าสุดที่ IMF publish (ปัจจุบัน household/NFC ถึง 2023, government ถึง 2024) |
| `IMF_only/thailand_debt_imf.png` | กราฟจากสคริปต์ข้างต้น |
| `thailand_debt_alt_sources_2024_2025.py` | ส่วนขยายปี 2024-2025 ที่ IMF GDD ยังไม่ publish — ทดสอบแหล่งข้อมูลสำรอง (BIS, BOT, PDMO, CEIC) แล้วต่อกับ IMF GDD **แบบมีเงื่อนไข** (ดูหัวข้อ "กติกาการต่อ series" ด้านล่าง) |
| `thailand_debt_2024_2025_extension.png` | กราฟจากสคริปต์ข้างต้น |

**เจตนาที่แยก 2 สคริปต์ออกจากกัน**: IMF GDD (annual) กับแหล่งข้อมูลสำรอง (quarterly,
คนละ methodology) ไม่ควรถูกดึง/ต่อกันแบบ silent ในสคริปต์เดียว — แยกให้ตรวจสอบ
ที่มาของแต่ละตัวเลขได้ง่าย และถ้าแหล่งสำรองพัง (endpoint เปลี่ยน) จะไม่กระทบ
ส่วน IMF ที่เสถียรกว่า

---

### ทฤษฎี / ที่มาของตัวเลข

**IMF Global Debt Database (GDD)** — ใช้ methodology ของ Mbaye, Badia & Chae (IMF WP),
รวบรวมหนี้ 3 sector (household, non-financial corporate, general government) เป็น
% of GDP โดยอิง BIS Total Credit Statistics และข้อมูลธนาคารกลางประเทศนั้นๆ เป็นหลัก
เข้าถึงได้ผ่าน DataMapper API (`imf.org/external/datamapper/api/v1/{INDICATOR}/{ISO3}`)
โดยไม่ต้อง auth

**BIS Total Credit Statistics (WS_TC)** — แหล่งข้อมูล underlying ที่ IMF GDD ใช้เป็น
หลักอยู่แล้ว (เห็นได้จากตัวเลข total ที่ตรงกันเกือบสนิทในช่วง overlap) เผยแพร่ราย
ไตรมาส อัปเดตเร็วกว่า IMF GDD มาก (มีถึงล่าสุด ~1-2 ไตรมาสก่อนปัจจุบัน) แบ่งตาม
"borrower" sector: `H` = household, `N` = non-financial corporate, `P` = private
non-financial (H+N รวมกัน), `C` = total non-financial (private + government),
`G` = general government — **แต่ Thailand ไม่มี series `G` เผยแพร่ตรงๆ** จึงต้อง
derive ด้วยสมการ **`G = C − P`** (ถูกต้องตาม definition ของ BIS เอง เพราะ
`C = P + G` เสมอ) แล้ว cross-check กับ IMF GDD government ย้อนหลังพบว่าตรงกัน
ในทุกปีที่มี overlap (diff < 1.1pp) — ยืนยันว่า derive ได้ถูกต้อง

**Total non-financial debt = household + NFC + government** บวกกันตรงๆ ได้เพราะ
ทั้ง 3 ตัวมาจาก methodology เดียวกัน (BIS/IMF GDD) ไม่ double-count ข้าม sector —
**ห้ามเอาตัวเลข government จาก PDMO/BOT มาบวกรวมกับ household/NFC จาก IMF/BIS**
เพราะเป็นคนละ perimeter (ดูหัวข้อถัดไป)

**Government debt: สองนิยามที่ไม่เท่ากัน — สำคัญมาก ห้ามสลับใช้:**
- **IMF GDD / BIS "government"** = เครดิตที่ให้กับภาครัฐจากผู้ให้กู้ทุกประเภท
  (BIS credit-statistics perimeter)
- **BOT/PDMO "public debt"** = หนี้สาธารณะตาม พ.ร.บ. บริหารหนี้สาธารณะ (รวม/ไม่รวม
  หนี้รัฐวิสาหกิจ, หนี้ FIDF ค้ำประกัน ฯลฯ — perimeter ต่างจาก BIS)

  ตัวเลข 2 แหล่งนี้**ใกล้เคียงกันโดยบังเอิญในบางปี แต่ไม่ใช่ตัวเดียวกัน** — ถ้าต่าง
  กันเกิน **10pp** ให้ print warning (แต่ไม่ใช่แปลว่าตัวใดตัวหนึ่งผิด อาจเป็นเพราะ
  perimeter ต่างกันจริง) ทุกกราฟที่มีเส้น government ต้อง label ชื่อ metric ให้ชัด
  (เช่น "General govt. credit (BIS derived: C−P)") ไม่ใช่เขียนรวมๆ ว่า
  "Government Debt" เฉยๆ

---

### วิธีอ่านกราฟ

**เส้น (4 เส้นหลัก, ทุกกราฟ):**
- สีน้ำเงิน = household, สีส้ม = NFC, สีเขียว = government, **สีดำเส้นหนา** = total
  (แยกจาก component ด้วยความหนาเส้น ไม่ใช่แค่สี — ให้เห็นชัดแม้ print ขาวดำ)
- แกน Y เริ่มที่ 0 เสมอ (ไม่ crop) และแบ่งสเกลทีละ 10 — เพื่อไม่ให้ magnitude หลอกตา
- เส้นทึบ (solid) = actual data จากแหล่งหลัก (IMF GDD)
- จุดข้อมูลรูปเพชร (◇, marker="D", ไม่ fill) = ปีที่เป็น **IMF projection**
  (ตรวจจาก field `estimatesStart` ใน response — ถ้า IMF ยังไม่ publish
  `estimatesStart` ให้กับ series ไหน จะไม่มี marker นี้ปรากฏ ไม่ใช่ว่าไม่ปีไหนเป็น
  projection จริงๆ)
- เส้นประ (`--`, marker สี่เหลี่ยม) = ส่วนขยายจากแหล่งข้อมูลสำรอง (BIS) ที่ผ่าน
  overlap check แล้ว → ต่อกับเส้น IMF ได้อย่างมั่นใจ
- เส้นจุดไข่ปลา (`:`, marker สามเหลี่ยม, โปร่งแสง) = ส่วนขยายที่**ไม่ผ่าน** overlap
  check → แสดงไว้เพื่อ reference เท่านั้น **ไม่ใช่ส่วนต่อเนื่องของเส้นเดิม** (ดูกติกา
  การต่อ series ด้านล่าง)
- เส้นแนวตั้งจุดสีเทา = จุดสลับแหล่งข้อมูล (ปี 2023: IMF GDD → BIS)

**แผงล่าง (volume bar — YoY change ของ total debt):**
- แท่ง**สีแดง** = ปีที่หนี้รวมเพิ่มขึ้นจากปีก่อน (YoY Δ ≥ 0)
- แท่ง**สีเขียว** = ปีที่หนี้รวมลดลงจากปีก่อน (YoY Δ < 0)
- หน่วยแท่ง = percentage point ของ GDP ที่เปลี่ยนไปในปีนั้น (ไม่ใช่ % change)
- แกน Y ของแท่งก็แบ่งสเกลทีละ 10 เช่นกัน เพื่อเทียบ scale กับกราฟบนได้ตรงๆ
- ปีที่ total คำนวณไม่ได้ (เพราะบาง component ยังไม่มีข้อมูล เช่น 2024 ใน IMF-only
  series) จะไม่มีแท่ง — ไม่ fabricate ตัวเลข

---

### ข้อตกลง / กติกาที่ใช้ตลอดทั้งโปรเจกต์ (ห้ามข้าม)

1. **ห้าม silent fail**: endpoint ไหน 404 / ไม่มี key ประเทศ / response ว่าง →
   `raise RuntimeError` พร้อมบอกชัดว่า indicator ไหนพัง และเพราะอะไร ไม่ plot
   กราฟที่ขาดเส้นเงียบๆ
2. **ต้อง print raw data table ก่อน plot เสมอ** — เพื่อให้ตรวจตัวเลขได้ก่อนเชื่อกราฟ
   พร้อม source column เมื่อดึงจากหลายแหล่ง
3. **Sanity check government debt กับ BOT/PDMO ทุกครั้ง** — ถ้าต่างเกิน **10pp**
   print warning (พร้อมอธิบายว่าอาจเป็นเพราะ perimeter ต่างกัน ไม่ใช่ error เสมอไป)
4. **กติกาการต่อ series ข้ามแหล่งข้อมูล (สำคัญที่สุด)**:
   - ก่อนต่อเส้นสองแหล่งเข้าด้วยกัน ต้องเช็ค **overlap ปีที่มีข้อมูลทั้งสองแหล่ง**
     (ในโปรเจกต์นี้คือปี 2023) เทียบตัวเลขกันก่อนเสมอ
   - diff **≤ 3pp** → ต่อได้ปกติ
   - diff **> 3pp ถึง 5pp** → ต่อได้แต่ print warning ว่า methodology เริ่มต่างกัน
   - diff **> 5pp** → **ห้ามต่อเส้นตรงๆ** ต้องแสดงเป็นเส้นแยก/ไม่ต่อเนื่อง (dotted +
     marker ต่าง) พร้อม print warning ชัดเจนว่าทำไมถึงไม่ต่อ
   - ผลจากเงื่อนไขนี้ในข้อมูลจริง: **household และ NFC ต่อไม่ได้** (diff 5.4pp,
     5.8pp) แต่ **government และ total ต่อได้** (diff 0.6pp, 1.0pp)
5. **ห้ามเอาตัวเลขจากคนละ perimeter มาบวกรวมกันข้าม sector** (เช่น PDMO government
   + BIS household) แม้ทั้งคู่จะเป็น % of GDP เหมือนกัน
6. **ทุกสคริปต์ต้องรันได้อิสระ (self-contained)** — สคริปต์ส่วนขยาย
   (`thailand_debt_alt_sources_2024_2025.py`) hardcode ค่าที่ verify แล้วจาก
   IMF GDD ไว้ในตัวเอง แทนที่จะเรียก IMF API ซ้ำ เพื่อไม่ให้ผลลัพธ์เปลี่ยนถ้า IMF
   แก้ตัวเลขย้อนหลังโดยไม่รู้ตัว (ต้อง sync มือถ้า IMF publish ปีใหม่)
7. **เมื่อ URL ที่ได้รับมาใช้ไม่ได้ ห้ามข้าม/assume เงียบๆ** — ต้องทดสอบจริง, print
   ว่า fail เพราะอะไร (404 / ไม่มี key ประเทศ / ต้อง auth / ต้อง postback ฯลฯ),
   แล้วค่อยหา endpoint ที่ถูกต้องจริงมาแทน (เช่นกรณี BIS: URL ในโจทย์
   `data.bis.org/topics/...` เป็น web-app route ใช้ไม่ได้ → หาเจอ SDMX REST
   endpoint จริงที่ `stats.bis.org/api/v1/data/WS_TC/...` จาก API docs)
8. **แหล่งที่ไม่มี machine-readable API (BOT, PDMO)** — report ตรงๆ ว่าต้อง manual
   entry จาก press release/PDF แทนที่จะพยายาม scrape HTML แบบเปราะบาง (ASPX
   postback / CMS ที่ไม่มี stable structure)

---

### วิธีรัน

```bash
python IMF_only/thailand_debt_imf.py
python thailand_debt_alt_sources_2024_2025.py
```

ต้องมี `requests`, `pandas`, `matplotlib` (ตรวจสอบด้วย
`python -c "import requests, pandas, matplotlib"`)
