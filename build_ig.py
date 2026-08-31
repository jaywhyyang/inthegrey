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


def _ai_comment():
    """ai_comment.json(진단)을 읽어 상단 코멘트 박스 HTML. 없으면 빈 문자열."""
    try:
        d = json.load(io.open(os.path.join(BASE, "ai_comment.json"), encoding="utf-8"))
    except Exception:
        return ""
    text = (d.get("text") or "").strip()
    if not text:
        return ""
    body = "".join(f"<p>{ln}</p>" for ln in text.split("\n") if ln.strip())
    watch = (d.get("watch") or "").strip()
    wh = f'<div class="watch"><b>관전 포인트</b> {watch}</div>' if watch else ""
    return (f'<div class="diag"><div class="dh">🔎 지금 진단<span>{d.get("updated","")}</span></div>'
            f'{body}{wh}</div>')


def _mini_spark(series, color="var(--muted)", W=132, H=26):
    """작품별 예매 추세 미니 스파크라인(자기 min~max로 정규화)."""
    ys = [v for _, v in series]
    if len(ys) < 2:
        return f'<svg viewBox="0 0 {W} {H}" width="100%" style="display:block;height:26px"></svg>'
    lo, hi = min(ys), max(ys)
    rng = (hi - lo) or 1
    pts = [f"{2 + i*(W-4)/(len(ys)-1):.1f},{H-3 - (v-lo)/rng*(H-6):.1f}" for i, v in enumerate(ys)]
    lx, ly = pts[-1].split(",")
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="none" style="display:block;height:26px">'
            f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="1.6"/>'
            f'<circle cx="{lx}" cy="{ly}" r="2.2" fill="{color}"/></svg>')


def _coopen_section(open_date="2026-09-02"):
    """같은 날(9/2) 개봉작 예매 '증가 추세' — competitors_hourly.csv 전체 시계열."""
    import datetime as _dt
    try:
        rows = list(csv.reader(io.open(os.path.join(BASE, "competitors_hourly.csv"), encoding="utf-8-sig")))
    except Exception:
        return ""
    data = [x for x in rows[1:] if x and len(x) >= 7]
    if not data:
        return ""
    ts_latest = data[-1][0]
    latest = {x[2]: x for x in data if x[0] == ts_latest and open_date in (x[3] or "")}
    if not latest:
        return ""

    def parse(t):
        try:
            return _dt.datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

    items = []
    for nm, x in latest.items():
        s = [(r[0], _num(r[5]) or 0) for r in data if r[2] == nm and _num(r[5]) is not None]
        cur = _num(x[5]) or 0
        g = None
        tl = parse(s[-1][0]) if s else None
        if tl and len(s) >= 2:
            ago = tl - _dt.timedelta(hours=24)
            prev = None
            for t, v in s:
                pt = parse(t)
                if pt and pt <= ago:
                    prev = v
            if prev is None:
                prev = s[0][1]                # 24h 데이터 없으면 최초 관측값 대비
            g = cur - prev
        items.append((nm, cur, x[4], g, s))
    items.sort(key=lambda z: -z[1])
    lis = []
    for nm, cur, rt, g, s in items:
        me = "그레이" in nm
        spark = _mini_spark(s, "var(--accent)" if me else "var(--muted)")
        if g is None:
            gtxt = ""
        elif g >= 0:
            gtxt = f'<span class="g">+{g:,}</span>'
        else:
            gtxt = f'<span class="g dn">{g:,}</span>'
        lis.append(f'<div class="cmp{" me" if me else ""}">'
                   f'<div class="cn">{nm[:18]}{" ★" if me else ""}</div>'
                   f'<div class="csp">{spark}</div>'
                   f'<div class="cv">{cur:,}{gtxt}</div></div>')
    return (f'<div class="panel"><h2>9/2 동시개봉작 예매 증가 추세 (같은 날 {len(items)}편)</h2>{"".join(lis)}'
            f'<div class="empty" style="padding:10px 0 0;text-align:left">선=각 작품 예매 추세(수집 시작~현재) · '
            f'우측=현재 예매관객(+지난 24h 증가) · ★ 인 더 그레이. 같은 날 스크린·주목도를 나눠 갖는 직접 경쟁작입니다.</div></div>')


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
        prev_day = None
        prev_lbl_day = None
        for i, (t, d, cum_i) in enumerate(deltas):
            cx = 6 + i * bw
            x = cx + bw * 0.16
            bh = abs(d) / span * plot_h
            by = (y0 - bh) if d >= 0 else y0
            col = "var(--accent)" if d >= 0 else "#e06a6a"
            day_i = t[:5]                                      # 'MM-DD'
            if prev_day is not None and day_i != prev_day:     # 날짜 경계: 세로 구분선 + 날짜
                _m, _dd = day_i.split("-")
                parts.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{PT-10:.1f}" y2="{H-PB+8:.1f}" '
                             f'stroke="var(--muted)" stroke-width="1" stroke-dasharray="2 3" opacity=".55"/>')
                parts.append(f'<text x="{cx+3:.1f}" y="{PT-1:.1f}" fill="var(--muted)" font-size="9.5" '
                             f'font-weight="700">{int(_m)}/{int(_dd)}</text>')
            prev_day = day_i
            parts.append(f'<rect x="{x:.1f}" y="{by:.1f}" width="{bw*0.68:.1f}" height="{max(bh,0.8):.1f}" '
                         f'rx="1.5" fill="{col}"><title>{t} · 순증 {d:+,} · 누적 {cum_i:,}</title></rect>')
            if i % step == 0 or i == n - 1:
                mid = cx + bw / 2
                ly = (by - 4) if d >= 0 else (by + bh + 11)                       # 순증(막대 위/아래)
                parts.append(f'<text x="{mid:.1f}" y="{ly:.1f}" text-anchor="middle" '
                             f'fill="var(--ink)" font-size="10.5" font-weight="700">{d:+,}</text>')
                parts.append(f'<text x="{mid:.1f}" y="{H-20:.1f}" text-anchor="middle" '     # 그 시점 누적
                             f'fill="var(--muted)" font-size="10" font-weight="600">{cum_i:,}</text>')
                _m, _dd = day_i.split("-")
                tlbl = (f"{int(_m)}/{int(_dd)} " if day_i != prev_lbl_day else "") + t[6:]  # 날짜 바뀌면 M/D 병기
                prev_lbl_day = day_i
                parts.append(f'<text x="{mid:.1f}" y="{H-7:.1f}" text-anchor="middle" '        # 시각(M/D HH:MM)
                             f'fill="var(--muted)" font-size="9">{tlbl}</text>')
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
    html = html.replace("__COMMENT__", _ai_comment())
    html = html.replace("__COOPEN__", _coopen_section())
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
  .diag{background:linear-gradient(135deg,#20263a 0%,#171b24 75%);border:1px solid #33406a;
    border-radius:16px;padding:18px 20px;margin-top:12px}
  .diag .dh{font-weight:750;font-size:14px;color:#aab6ff;margin-bottom:8px;display:flex;
    justify-content:space-between;align-items:baseline}
  .diag .dh span{font-size:11px;color:var(--muted);font-weight:400}
  .diag p{font-size:14px;line-height:1.75;margin:.35em 0;color:var(--ink)}
  .diag .watch{margin-top:10px;padding-top:10px;border-top:1px solid var(--line);font-size:13px;color:var(--muted)}
  .diag .watch b{color:#8b9dff}
  .cmp{display:flex;align-items:center;gap:10px;margin:7px 0;font-size:13px}
  .cmp .cn{width:150px;flex:none;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .cmp .csp{flex:1;min-width:80px;opacity:.75}
  .cmp .cv{width:96px;flex:none;text-align:right;font-variant-numeric:tabular-nums}
  .cmp .cv .g{display:inline-block;margin-left:5px;font-size:10.5px;color:var(--good);font-weight:600}
  .cmp .cv .g.dn{color:#e06a6a}
  .cmp.me{background:rgba(139,157,255,.06);border-radius:10px;padding:4px 8px;margin-left:-8px;margin-right:-8px}
  .cmp.me .cn{color:var(--ink);font-weight:750}
  .cmp.me .csp{opacity:1}
  .cmp.me .cv{color:#aab6ff;font-weight:750}
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

  __COMMENT__

  <div class="panel">
    <h2>시간당 예매 순증 (막대=순증분 · 아래=그 시점 누적)</h2>
    __SPARK__
  </div>

  __COOPEN__

  <div class="panel">
    <h2>흥행 기대 밴드 (메가박스 단독개봉 comp)</h2>
    <div class="band"><span>하방 __BLO__</span><div class="bar"></div><span>최대 사례 __BHI__</span></div>
    <div class="empty" style="padding:8px 0 0;text-align:left">중심 밴드 <b>__BMIDLO__–__BMIDHI__명</b> · 상방 시나리오 __BHIGH__ · 실사 외화 단독 최고 사례 __BHI__ · 개봉 후 실측으로 좁혀갑니다__BSRC__.</div>
  </div>

  <div class="foot"><span class="dot"></span>1시간 단위 자동 갱신 · 마지막 갱신 __UPD__</div>
</div></body></html>"""


if __name__ == "__main__":
    print("생성:", generate())
