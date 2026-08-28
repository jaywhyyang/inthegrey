# -*- coding: utf-8 -*-
"""
인 더 그레이(2026-09-02 개봉) 개봉 전/후 실시간 예매 트래커 대시보드.
inthegrey_hourly.csv(실시간 예매 스냅샷)를 읽어 자체 완결형 index.html 생성.
- 개봉 전: 예매관객 빌드업 + 예매율/순위 추세.
- 벤치마크 밴드는 ../그린랜드2/megabox_solo_band.json 에서 매 빌드마다 읽는다(하드코딩 금지).
- 프로모 분해는 SHOW_ORGANIC=False 로 공개 페이지에서 가린다(집행 장수 역산 방지).
"""
import os, csv, io, re, json, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE, "inthegrey_hourly.csv")
OUT_PATH = os.path.join(BASE, "index.html")

OPEN_DATE = datetime.date(2026, 9, 2)
PROMO_BASE = 3000          # 1주차 티켓 프로모션(집행 완료) — 이 위가 실예매(organic)
# [내부 정보] 2주차 +1,000장 추가 예정(현재는 미집행, 공개 표기 안 함)
# 실예매(프로모 제외) 공개 여부.
# 트레이드오프: 누적 예매는 KOBIS 공개 데이터라 누구나 조회할 수 있다. 따라서 실예매를
# 표시하면 KOBIS 누적에서 빼는 것만으로 프로모 집행 장수가 정확히 역산된다.
# 우리 페이지에서 누적을 숨겨도 마찬가지라, 표시/비표시의 양자택일이다.
# 2026-08-28 사용자 결정: 공개(True). 프로모 집행 사실과 규모 노출을 감수한다.
SHOW_ORGANIC = True
# ── 흥행 기대 밴드 ────────────────────────────────────────────────────────────
# 숫자를 여기에 손으로 적지 말 것. 출처는 그린랜드2 프로젝트의 comp 분석이고,
# megabox_solo_band.json 이 유일한 진실이다(build_megabox_solo.py 실행 시 자동 갱신).
# 손으로 옮겨 적으면 워페어 종영 등으로 comp 가 바뀔 때 반드시 드리프트한다.
# 아래 상수는 교환 파일을 못 읽을 때만 쓰는 폴백이며, 그 경우 페이지에 기준일이 안 찍힌다.
#
# 파일은 이 리포 안에 커밋돼 있다(자립). 그린랜드2 분석을 돌리면 이 사본까지 같이 갱신되므로,
# 평소에는 이 폴더만으로 작업하면 되고 그린랜드2 폴더가 없어도 동작한다.
# 둘 다 있으면 더 최근 것을 쓴다 — 분석을 방금 돌렸는데 사본 커밋을 잊은 경우를 흡수한다.
BAND_LOCAL = os.path.join(BASE, "megabox_solo_band.json")
BAND_UPSTREAM = os.path.join(BASE, "..", "그린랜드2", "megabox_solo_band.json")


def _band_path():
    cands = [p for p in (BAND_LOCAL, BAND_UPSTREAM) if os.path.exists(p)]
    return max(cands, key=os.path.getmtime) if cands else BAND_LOCAL
BAND_LO, BAND_MID_LO, BAND_MID_HI, BAND_HIGH, BAND_CEIL = 15000, 20000, 25000, 34000, 63767
BAND_SRC = ""      # 교환 파일에서 읽었을 때 기준일·표본수


def load_band():
    """교환 파일에서 밴드를 읽어 전역 상수를 덮어쓴다. 실패해도 폴백으로 진행."""
    global BAND_LO, BAND_MID_LO, BAND_MID_HI, BAND_HIGH, BAND_CEIL, BAND_SRC
    try:
        with io.open(_band_path(), encoding="utf-8") as f:
            d = json.load(f)
        sc, ob, seg = d["scenario"], d["observed"], d["segment"]
        BAND_LO = int(round(sc["low"] * 0.8, -3))     # 편성이 가정보다 좁을 때의 하방
        BAND_MID_LO = int(round(sc["low"], -3))
        BAND_MID_HI = int(round(sc["mid"], -3))
        BAND_HIGH = int(round(sc["high"], -3))
        BAND_CEIL = int(sc["ceiling"])
        BAND_SRC = "comp {0}편 · {1} 기준".format(seg["n"], d["data_range"]["end"])
        return d
    except Exception as e:
        print("  !! 밴드 교환 파일을 못 읽어 폴백 사용:", e)
        return None


def _num(s):
    try:
        return int(re.sub(r"[^\d]", "", str(s)))
    except Exception:
        return None


def _rows():
    if not os.path.exists(CSV_PATH):
        return []
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        rd = list(csv.reader(f))
    return [r for r in rd[1:] if r and len(r) >= 8 and r[1]]  # 순위 있는 유효행


def generate(csv_path=CSV_PATH, out_path=OUT_PATH):
    load_band()   # 밴드는 매 빌드마다 교환 파일에서 다시 읽는다
    rows = _rows()
    today = datetime.date.today()
    dday = (OPEN_DATE - today).days
    ddtxt = (f"D-{dday}" if dday > 0 else ("D-DAY" if dday == 0 else f"개봉 {-dday}일차"))

    book = rank = rate = cum = 0
    upd = ""
    series = []  # (label, 예매관객)
    if rows:
        last = rows[-1]
        rank = _num(last[1]) or 0
        rate = last[4] if len(last) > 4 else ""
        book = _num(last[7]) if len(last) > 7 else 0
        cum = _num(last[8]) if len(last) > 8 else 0
        upd = last[0][:16]
        for r in rows:
            b = _num(r[7]) if len(r) > 7 else None
            if b is not None:
                series.append((r[0][5:16], b))
    organic = max(0, (book or 0) - PROMO_BASE)

    # 시간당 예매 순증(구간별 net add) — 막대 + 값/시각 라벨 + 마우스오버 툴팁.
    # 순증(예매 유입)은 위(파랑), 순감(취소 등)은 아래(빨강), 0 기준선 대비. 누적은 히어로에 있음.
    spark = ""
    # (시각, 순증, 그 시점 누적)
    deltas = [(series[i][0], series[i][1] - series[i - 1][1], series[i][1]) for i in range(1, len(series))]
    if deltas:
        n = len(deltas)
        W, H, PT, PB = 680, 164, 26, 34
        dmax = max(d for _, d, _c in deltas)
        dmin = min(d for _, d, _c in deltas)
        hi, lo = max(dmax, 0), min(dmin, 0)
        span = (hi - lo) or 1
        plot_h = H - PT - PB
        y0 = PT + (hi / span) * plot_h            # 0 기준선(순감 있으면 자동으로 내려감)
        bw = (W - 12) / n
        step = max(1, (n + 13) // 14)             # 라벨 과밀 방지(항상 보이는 값은 최대 ~14개, 툴팁은 전부)
        parts = [f'<line x1="6" x2="{W-6}" y1="{y0:.1f}" y2="{y0:.1f}" stroke="var(--line)" stroke-width="1"/>']
        for i, (t, d, cum_i) in enumerate(deltas):
            cx = 6 + i * bw
            x = cx + bw * 0.16
            bh = abs(d) / span * plot_h
            by = (y0 - bh) if d >= 0 else y0
            col = "var(--accent)" if d >= 0 else "#e06a6a"
            parts.append(f'<rect x="{x:.1f}" y="{by:.1f}" width="{bw*0.68:.1f}" height="{max(bh,0.8):.1f}" '
                         f'rx="1.5" fill="{col}"><title>{t} · 순증 {d:+,} · 누적 {cum_i:,}</title></rect>')
            if i % step == 0 or i == n - 1:
                mid = cx + bw / 2
                ly = (by - 4) if d >= 0 else (by + bh + 11)                       # 순증(막대 위/아래)
                parts.append(f'<text x="{mid:.1f}" y="{ly:.1f}" text-anchor="middle" '
                             f'fill="var(--ink)" font-size="10.5" font-weight="700">{d:+,}</text>')
                parts.append(f'<text x="{mid:.1f}" y="{H-20:.1f}" text-anchor="middle" '     # 그 시점 누적
                             f'fill="var(--muted)" font-size="10" font-weight="600">{cum_i:,}</text>')
                parts.append(f'<text x="{mid:.1f}" y="{H-7:.1f}" text-anchor="middle" '        # 시각(HH:MM)
                             f'fill="var(--muted)" font-size="9">{t[6:]}</text>')
        badge = (f'<text x="{W-8}" y="13" text-anchor="end" fill="var(--muted)" font-size="11">'
                 f'최근 {deltas[-1][0]} · {deltas[-1][1]:+,} → 누적 {deltas[-1][2]:,}</text>')
        spark = (f'<svg viewBox="0 0 {W} {H}" width="100%" style="display:block;height:auto;overflow:visible">'
                 f'{"".join(parts)}{badge}</svg>')

    html = _TPL
    html = html.replace("__DDAY__", ddtxt)
    html = html.replace("__BOOK__", f"{book:,}" if book else "—")
    if SHOW_ORGANIC:
        note = (f"이 중 실예매(프로모 {PROMO_BASE:,}장 제외) <b>{organic:,}명</b>"
                if book else "이 중 실예매 —")
    else:
        note = "KOBIS 실시간 예매 기준 · 개봉일 이전 선예매 포함"
    html = html.replace("__NOTE__", note)
    html = html.replace("__RATE__", rate or "—")
    html = html.replace("__RANK__", (f"{rank}위" if rank else "—"))
    html = html.replace("__CUM__", (f"{cum:,}" if cum else "—"))
    html = html.replace("__SPARK__", spark or '<div class="empty">예매 추세는 수집이 몇 시간 쌓이면 표시됩니다</div>')
    html = html.replace("__UPD__", upd or "수집 대기 중")
    html = (html.replace("__BLO__", f"{BAND_LO:,}").replace("__BHI__", f"{BAND_CEIL:,}")
            .replace("__BMIDLO__", f"{BAND_MID_LO:,}").replace("__BMIDHI__", f"{BAND_MID_HI:,}")
            .replace("__BHIGH__", f"{BAND_HIGH:,}")
            .replace("__BSRC__", (" · " + BAND_SRC) if BAND_SRC else ""))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


_TPL = """<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>인 더 그레이 — 실시간 예매 트래커</title>
<style>
  :root{color-scheme:light dark;
    --bg:#0e1016;--surface:#171b24;--ink:#e9ebf0;--muted:#9aa2b0;--line:#262c38;
    --accent:#8b9dff;--accent2:#5f7bff;--good:#4ade80}
  *{box-sizing:border-box;margin:0;padding:0}
  body{min-height:100vh;font-family:-apple-system,"Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;
    background:radial-gradient(1100px 520px at 50% -12%,#1b2436 0%,#0e1016 60%);color:var(--ink);
    padding:26px 18px 60px}
  .wrap{max-width:720px;margin:0 auto}
  .top{text-align:center;margin-bottom:22px}
  .dday{display:inline-block;font-weight:800;font-size:13px;letter-spacing:.06em;color:#0e1016;
    background:linear-gradient(90deg,#aab6ff,#8b9dff);padding:5px 14px;border-radius:999px}
  h1{font-size:26px;font-weight:850;letter-spacing:-.02em;margin:14px 0 4px}
  .sub{color:var(--muted);font-size:13.5px}
  .grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin:20px 0}
  .card{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:18px}
  .card .k{font-size:12.5px;color:var(--muted);margin-bottom:6px;letter-spacing:.02em}
  .card .v{font-size:30px;font-weight:850;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
  .card.hero{grid-column:1/3;background:linear-gradient(135deg,#1a2440 0%,#171b24 70%);border-color:#2f3d63}
  .card.hero .v{font-size:44px;color:#aab6ff}
  .card .note{font-size:12px;color:var(--muted);margin-top:5px}
  .card .v.good{color:var(--good)}
  .panel{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:18px;margin-top:12px}
  .panel h2{font-size:14px;font-weight:750;margin-bottom:10px;color:var(--muted);letter-spacing:.02em}
  .empty{color:var(--muted);font-size:13px;text-align:center;padding:30px 0}
  .band{display:flex;align-items:center;gap:10px;margin-top:8px;font-size:13px}
  .bar{flex:1;height:8px;border-radius:99px;background:linear-gradient(90deg,#3a4260,#8b9dff);position:relative}
  .foot{text-align:center;color:var(--muted);font-size:11.5px;margin-top:22px;line-height:1.7}
  .dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--good);margin-right:6px;
    box-shadow:0 0 0 0 rgba(74,222,128,.5);animation:b 2.4s infinite}
  @keyframes b{70%{box-shadow:0 0 0 7px rgba(74,222,128,0)}100%{box-shadow:0 0 0 0 rgba(74,222,128,0)}}
</style></head>
<body><div class="wrap">
  <div class="top">
    <span class="dday">🎬 __DDAY__</span>
    <h1>인 더 그레이</h1>
    <div class="sub">2026-09-02 개봉 · 메가박스 단독 · 실시간 예매 트래커</div>
  </div>

  <div class="grid">
    <div class="card hero">
      <div class="k">예매 관객 (누적)</div>
      <div class="v">__BOOK__</div>
      <div class="note">__NOTE__</div>
    </div>
    <div class="card"><div class="k">예매율</div><div class="v">__RATE__</div></div>
    <div class="card"><div class="k">예매 순위</div><div class="v">__RANK__</div></div>
  </div>

  <div class="panel">
    <h2>시간당 예매 순증 (막대=순증분 · 아래=그 시점 누적)</h2>
    __SPARK__
  </div>

  <div class="panel">
    <h2>흥행 기대 밴드 (메가박스 단독개봉 comp)</h2>
    <div class="band"><span>하방 __BLO__</span><div class="bar"></div><span>최대 사례 __BHI__</span></div>
    <div class="empty" style="padding:8px 0 0;text-align:left">중심 밴드 <b>__BMIDLO__–__BMIDHI__명</b> · 상방 시나리오 __BHIGH__ · 실사 외화 단독 최고 사례 __BHI__ · 개봉 후 실측으로 좁혀갑니다__BSRC__.</div>
  </div>

  <div class="foot"><span class="dot"></span>1시간 단위 자동 갱신 · 마지막 갱신 __UPD__</div>
</div></body></html>"""


if __name__ == "__main__":
    print("생성:", generate())
