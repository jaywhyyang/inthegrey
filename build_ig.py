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
    # '관전 포인트' 문단은 아래 watch 줄과 중복이라 본문에서 제외
    body = "".join(f"<p>{ln}</p>" for ln in text.split("\n")
                   if ln.strip() and not ln.strip().startswith("관전 포인트"))
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


MEMBER_DETAIL = os.path.join(BASE, "member_detail.json")
MEMBER_SNAP = os.path.join(BASE, "member_snapshots.csv")


def _member_summary():
    """member_snapshots.csv 최신 행 → 오늘/누적 관객·상영·매출."""
    if not os.path.exists(MEMBER_SNAP):
        return None
    try:
        with open(MEMBER_SNAP, encoding="utf-8-sig", newline="") as f:
            rows = [r for r in csv.DictReader(f) if r.get("관객수")]
    except Exception:
        return None
    if not rows:
        return None
    last = rows[-1]
    out = {k: _num(last.get(k)) for k in
           ("관객수", "누적관객수", "무료관객수", "상영횟수", "스크린수", "매출액", "누적매출액")}
    out["날짜"] = last.get("날짜", "")
    return out


def _short_theater(name):
    for p in ("메가박스 ", "CGV ", "롯데시네마 "):
        if name.startswith(p):
            return name[len(p):]
    return name


_REGION_POS = {
    "서울특별시": (126, 86, "서울"), "인천광역시": (92, 96, "인천"),
    "경기도": (150, 114, "경기"), "강원도": (216, 80, "강원"),
    "강원특별자치도": (216, 80, "강원"),
    "충청북도": (178, 146, "충북"), "세종특별자치시": (138, 158, "세종"),
    "대전광역시": (158, 176, "대전"), "충청남도": (104, 160, "충남"),
    "경상북도": (218, 150, "경북"), "대구광역시": (208, 182, "대구"),
    "울산광역시": (252, 198, "울산"), "부산광역시": (238, 220, "부산"),
    "경상남도": (192, 212, "경남"), "전라북도": (132, 196, "전북"),
    "전북특별자치도": (132, 196, "전북"),
    "광주광역시": (106, 232, "광주"), "전라남도": (122, 252, "전남"),
    "제주도": (110, 316, "제주"), "제주특별자치도": (110, 316, "제주"),
}


def _daily_trend_section():
    """일별 추이 Chart.js 라인/막대 차트(그린랜드2 부활) — 일별 실관객·누적·편성·회당."""
    if not os.path.exists(MEMBER_SNAP):
        return ""
    try:
        rows = [r for r in csv.DictReader(open(MEMBER_SNAP, encoding="utf-8-sig")) if r.get("관객수")]
    except Exception:
        return ""
    byday = {}
    for r in rows:
        d = r.get("날짜")
        if not d:
            continue
        b = byday.setdefault(d, {"aud": 0, "cum": 0, "scr": 0, "shows": 0})
        b["aud"] = max(b["aud"], _num(r.get("관객수")) or 0)
        b["cum"] = max(b["cum"], _num(r.get("누적관객수")) or 0)
        b["scr"] = max(b["scr"], _num(r.get("스크린수")) or 0)
        b["shows"] = max(b["shows"], _num(r.get("상영횟수")) or 0)
    dates = sorted(byday)
    if len(dates) < 1:
        return ""
    today = datetime.date.today().strftime("%Y-%m-%d")
    data = []
    for d in dates:
        b = byday[d]
        data.append({"d": d[5:], "aud": b["aud"], "cum": b["cum"], "scr": b["scr"],
                     "shows": b["shows"], "per": round(b["aud"] / b["shows"], 1) if b["shows"] else 0,
                     "live": d == today})
    payload = json.dumps(data, ensure_ascii=False)
    return (
        '<div class="panel"><h2>📈 일별 추이 (실관객·누적·편성)</h2>'
        '<div class="cbox"><canvas id="c_daily"></canvas></div>'
        '<div class="cbox" style="margin-top:10px"><canvas id="c_supply"></canvas></div>'
        '<div class="empty" style="padding:6px 0 0;text-align:left">막대=그날 실관객/편성, 선=누적/회당관객. 옅은 막대=진행 중(오늘).</div></div>'
        '<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>'
        '<script>(function(){var D=' + payload + ';'
        'if(!window.Chart||!D.length)return;'
        'Chart.defaults.color="#9aa2b0";Chart.defaults.font.size=11;'
        'var lb=D.map(function(x){return x.d});'
        'var barCol=D.map(function(x){return x.live?"rgba(139,157,255,.4)":"rgba(139,157,255,.85)"});'
        'var scrCol=D.map(function(x){return x.live?"rgba(126,224,168,.4)":"rgba(126,224,168,.85)"});'
        'var gx={grid:{color:"rgba(255,255,255,.06)"}};'
        'new Chart(document.getElementById("c_daily"),{data:{labels:lb,datasets:['
        '{type:"bar",label:"일별 실관객",data:D.map(function(x){return x.aud}),backgroundColor:barCol,yAxisID:"y",order:2},'
        '{type:"line",label:"누적 실관객",data:D.map(function(x){return x.cum}),borderColor:"#f4c89a",backgroundColor:"#f4c89a",tension:.3,yAxisID:"y2",order:1}'
        ']},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{boxWidth:12}}},'
        'scales:{x:gx,y:{position:"left",grid:gx.grid,title:{display:true,text:"일별"}},'
        'y2:{position:"right",grid:{display:false},title:{display:true,text:"누적"}}}}});'
        'new Chart(document.getElementById("c_supply"),{data:{labels:lb,datasets:['
        '{type:"bar",label:"편성(상영관)",data:D.map(function(x){return x.scr}),backgroundColor:scrCol,yAxisID:"y",order:2},'
        '{type:"line",label:"회당 관객",data:D.map(function(x){return x.per}),borderColor:"#8b9dff",backgroundColor:"#8b9dff",tension:.3,yAxisID:"y2",order:1}'
        ']},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{boxWidth:12}}},'
        'scales:{x:gx,y:{position:"left",grid:gx.grid,title:{display:true,text:"상영관"}},'
        'y2:{position:"right",grid:{display:false},title:{display:true,text:"회당"}}}}});'
        '})();</script>')


def _region_map():
    """지역별 관객 규모 지도 — 위치형 버블 SVG(그린랜드2 부활)."""
    try:
        det = json.load(io.open(MEMBER_DETAIL, encoding="utf-8"))
    except Exception:
        return ""
    regions = det.get("regions") or []
    if not regions:
        return ""
    audmax = max((r[1] for r in regions), default=1) or 1

    def color(a):
        t = (a / audmax) ** 0.6
        c0, c1 = (0x33, 0x41, 0x55), (0xef, 0x44, 0x44)
        return "#%02x%02x%02x" % tuple(int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))

    body = ""
    for r in regions:
        name, aud = r[0], r[1]
        if name not in _REGION_POS:
            continue
        x, y, lbl = _REGION_POS[name]
        rad = 8 + (aud / audmax) ** 0.5 * 24
        body += (f'<circle cx="{x}" cy="{y}" r="{rad:.1f}" fill="{color(aud)}" fill-opacity="0.82" '
                 f'stroke="#0f1117" stroke-width="1"><title>{name} · 관객 {aud:,}</title></circle>'
                 f'<text x="{x}" y="{y-1}" text-anchor="middle" font-size="9" fill="#fff" font-weight="bold">{lbl}</text>'
                 f'<text x="{x}" y="{y+9}" text-anchor="middle" font-size="8" fill="#e7e9ee">{aud:,}</text>')
    if not body:
        return ""
    svg = f'<svg viewBox="0 0 300 340" style="width:100%;max-width:420px;display:block;margin:6px auto">{body}</svg>'
    return ('<div class="panel"><h2>🗺️ 지역별 관객 규모 지도</h2>' + svg +
            '<div class="empty" style="padding:6px 0 0;text-align:left">원 크기·색 = 관객수(<b style="color:#ef4444">빨강=많음</b>). '
            '어디서 많이 보는지 한눈에.</div></div>')


def _member_section():
    """회원통계(실관객) 섹션 — 개봉 후 데이터가 있을 때만 렌더(없으면 빈 문자열)."""
    try:
        det = json.load(io.open(MEMBER_DETAIL, encoding="utf-8"))
    except Exception:
        return ""
    if not det or not det.get("total"):
        return ""
    s = _member_summary() or {}
    total = det.get("total", 0)
    fill = det.get("fill_rate", 0)
    scr = det.get("screen_count", 0)
    today = s.get("관객수") or total
    cum = s.get("누적관객수") or total
    shows = s.get("상영횟수") or 0
    free = s.get("무료관객수") or 0
    paid = max(0, today - free)
    date = det.get("date") or s.get("날짜") or ""
    # ── 요약 카드 ──
    cards = (
        f'<div class="mstat"><div class="mh">🎟️ 개봉 실적 · 회원통계(실관객)<span>{date} 기준</span></div>'
        f'<div class="mgrid">'
        f'<div><b>{today:,}</b><span>오늘 관객</span></div>'
        f'<div><b>{cum:,}</b><span>누적 관객</span></div>'
        f'<div><b>{fill:.0f}%</b><span>좌석판매율</span></div>'
        f'<div><b>{scr}</b><span>상영관 · {shows}회</span></div>'
        f'</div>'
        + (f'<div class="mnote">유료 {paid:,} · 무료 {free:,}</div>' if free else '')
        + '</div>')
    # ── 관별 랭킹 ──
    theaters = det.get("theaters", [])[:15]
    tmax = max((t[1] for t in theaters), default=1) or 1
    trows = ""
    for name, aud, nscr in theaters:
        w = max(3, round(aud / tmax * 100))
        trows += (f'<div class="trow"><span class="tn">{_short_theater(name)}</span>'
                  f'<span class="tb"><i style="width:{w}%"></i></span>'
                  f'<span class="tv">{aud:,}<em>· {nscr}관</em></span></div>')
    rank_panel = (f'<div class="panel"><h2>관별 관객 랭킹 · 잘 드는 극장</h2>{trows}</div>'
                  if trows else "")
    # ── 회차(시간대) × 극장 히트맵 ──
    slots = det.get("slots", [])
    tslots = det.get("theater_slots", {})
    heat = ""
    if slots and any(slots):
        nsl = len(slots)
        cellmax = max((v for row in tslots.values() for v in row), default=1) or 1
        head = '<div class="hcell hh"></div>' + "".join(
            f'<div class="hcell hh">{i+1}회</div>' for i in range(nsl))
        # 전체(회차 합) 행
        smax = max(slots) or 1
        allrow = '<div class="hcell hn">전체</div>' + "".join(
            f'<div class="hcell" style="background:rgba(139,157,255,{0.10+0.85*(v/smax):.2f})">{v or ""}</div>'
            for v in slots)
        body = f'<div class="hrow">{head}</div><div class="hrow tot">{allrow}</div>'
        for name, aud, _ in theaters[:12]:
            row = tslots.get(name, [0] * nsl)
            cells = "".join(
                f'<div class="hcell" style="background:rgba(139,157,255,{(0.06+0.9*(v/cellmax)) if v else 0:.2f})">{v or ""}</div>'
                for v in (row + [0] * (nsl - len(row)))[:nsl])
            heat += f'<div class="hrow"><div class="hcell hn">{_short_theater(name)}</div>{cells}</div>'
        heat = (f'<div class="panel"><h2>시간대별(회차) × 극장 히트맵 · 진한 칸일수록 관객 집중</h2>'
                f'<div class="heat" style="grid-template-columns:120px repeat({nsl},1fr)">'
                f'{body}{heat}</div>'
                f'<div class="hleg">왼쪽=이른 회차 · 오른쪽=늦은 회차 · 숫자는 관객수</div></div>')
    # ── 지역 · 체인 ──
    regions = det.get("regions", [])[:6]
    rg = "".join(f'<div class="cmp"><span class="cn">{r[0]}</span>'
                 f'<span class="cv">{r[1]:,}<em style="color:var(--muted)"> · {r[3]:.0f}%</em></span></div>'
                 for r in regions)
    chains = det.get("chains", [])
    ch = "".join(f'<div class="cmp"><span class="cn">{c[0]}</span>'
                 f'<span class="cv">{c[3]:,}<em style="color:var(--muted)"> · {c[1]}관</em></span></div>'
                 for c in chains)
    rc_panel = (f'<div class="panel"><h2>지역 · 체인 (관객 · 좌석판매율/관수)</h2>'
                f'<div class="rc"><div>{rg}</div><div>{ch}</div></div></div>'
                if (rg or ch) else "")
    return cards + rank_panel + heat + rc_panel


DAILY_REPORT = os.path.join(BASE, "daily_report.json")


def _daily_report_card():
    """daily_report.json(build_daily_report.py 생성)을 읽어 상단 '어제 리포트' 카드."""
    try:
        d = json.load(io.open(DAILY_REPORT, encoding="utf-8"))
    except Exception:
        return ""
    txt = (d.get("text") or "").strip()
    if not txt:
        return ""
    # 이 카드는 세션에서 build_daily_report.py를 돌려야 갱신된다.
    # 안 돌리면 옛 날짜 리포트가 계속 상단에 남으므로, 어제 것이 아니면 아예 안 띄운다.
    try:
        rd = datetime.date.fromisoformat(str(d.get("date", "")).strip())
        if (datetime.date.today() - rd).days > 1:
            return ""
    except Exception:
        return ""
    paras = [p.strip() for p in txt.split("\n\n") if p.strip()]
    head = re.sub(r"\*([^*]+)\*", r"\1", paras[0]).replace("📊", "").strip()
    parts = []
    for p in paras[1:]:
        if p.startswith("📈"):
            continue
        parts.append("<p>" + re.sub(r"\*([^*]+)\*", r"<b>\1</b>", p) + "</p>")
    body = "".join(parts)
    upd = str(d.get("updated", ""))
    return ('<details class="drep"><summary class="dh">🗞️ ' + head +
            '<span>' + upd + ' · 펼치기</span></summary><div class="drepbody">' + body + '</div></details>')


def _comp_forward():
    """전날에서 '오늘 기대치'를 comp(그린랜드2 드롭률 + 페이싱)로 전방 예측.
    나우캐스트(후행)와 비교해 '예상보다 빠른/느린 하락'을 판정한다."""
    try:
        st = json.load(io.open(os.path.join(BASE, "report_state.json"), encoding="utf-8"))
        d = json.load(io.open(_band_path(), encoding="utf-8"))
    except Exception:
        return None
    open_ad = st.get("open_admits")
    finals = st.get("finals", {})
    if not open_ad or not finals:
        return None
    today = datetime.date.today()
    day_n = (today - OPEN_DATE).days + 1
    if day_n < 2:
        return None
    import math as _m
    mdl = d.get("model", {})
    pac = (d.get("pacing", {}) or {}).get("median", {})
    a, b = mdl.get("a"), mdl.get("b")
    if not (a and b):
        return None
    final = _m.exp(a + b * _m.log(open_ad))
    pts = sorted((int(k[1:]), v) for k, v in pac.items() if k.startswith("D"))
    pts = [(0, 0.0)] + pts

    def pcum(n):
        if n <= 0:
            return 0.0
        if n >= pts[-1][0]:
            return min(1.0, pts[-1][1])
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if x0 <= n <= x1:
                return y0 + (y1 - y0) * (n - x0) / (x1 - x0)
        return pts[-1][1]
    pace_today = (pcum(day_n) - pcum(day_n - 1)) * final    # 페이싱 기반 오늘 기대
    return {"day_n": day_n, "pace": int(round(pace_today)), "final": int(final)}


# 그린랜드2 회원통계 실측 시간대 누적비중 곡선 — 요일보정용 평일/주말 분리.
# (관객/그날최종 평균, benchmarks/greenland2/member_snapshots.csv)
_INTRA_WD = {0: .382, 1: .339, 2: .34, 3: .347, 4: .347, 5: .347, 6: .347, 7: .351,
             8: .367, 9: .508, 10: .606, 11: .619, 12: .656, 13: .741, 14: .787,
             15: .84, 16: .877, 17: .91, 18: .943, 19: .961, 20: .977, 21: .989,
             22: .997, 23: 1.0}   # 평일(월~목): 앞쪽 집중
_INTRA_WK = {0: .496, 1: .528, 2: .53, 3: .529, 4: .501, 5: .501, 6: .502, 7: .506,
             8: .518, 9: .541, 10: .577, 11: .607, 12: .654, 13: .694, 14: .738,
             15: .779, 16: .819, 17: .858, 18: .894, 19: .935, 20: .964, 21: .985,
             22: .996, 23: 1.0}   # 주말(금~일): 저녁 집중(더 평평)


def _intra_frac(h, dow=None):
    """시각 h(+요일 dow: 0=월)에서 그날 최종 대비 누적비중. 금~일은 주말 곡선."""
    tbl = _INTRA_WK if (dow is not None and dow >= 4) else _INTRA_WD
    hh = int(h)
    if hh >= 23:
        return 1.0
    f0, f1 = tbl[hh], tbl.get(hh + 1, 1.0)
    return f0 + (f1 - f0) * (h - hh)


def _pace_cum(n, pac):
    pts = sorted((int(k[1:]), v) for k, v in pac.items() if k.startswith("D"))
    if not pts:
        return None
    pts = [(0, 0.0)] + pts
    if n <= 0:
        return 0.0
    if n >= pts[-1][0]:
        return min(1.0, pts[-1][1])
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= n <= x1:
            return y0 + (y1 - y0) * (n - x0) / (x1 - x0)
    return pts[-1][1]


def _final_forecast():
    """진행 중 생애 최종 예측: 누적 실관객 ÷ 페이싱(경과 일수) + 개봉일 모델 + 감쇠 보정.
    주말 선예매 스냅샷을 맥락으로 함께 반환."""
    import math as _m
    snaps = []
    if os.path.exists(MEMBER_SNAP):
        try:
            snaps = [r for r in csv.DictReader(open(MEMBER_SNAP, encoding="utf-8-sig")) if r.get("누적관객수")]
        except Exception:
            snaps = []
    if not snaps:
        return None
    last = snaps[-1]
    cum = _num(last.get("누적관객수")) or 0
    if cum < 500:
        return None
    ts = last.get("수집시각", "")
    try:
        dt = datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        h = dt.hour + dt.minute / 60.0
        cur_date = dt.date()
    except Exception:
        return None
    day_n = (cur_date - OPEN_DATE).days + 1
    if day_n < 1:
        return None
    band = _band() if "_band" in globals() else None
    try:
        band = json.load(io.open(_band_path(), encoding="utf-8"))
    except Exception:
        return None
    mdl = band.get("model", {})
    pac = (band.get("pacing", {}) or {}).get("median", {})
    a, b = mdl.get("a"), mdl.get("b")
    st = {}
    try:
        st = json.load(io.open(os.path.join(BASE, "report_state.json"), encoding="utf-8"))
    except Exception:
        pass
    open_ad = st.get("open_admits")
    # 경과 일수(오늘 진행분 포함)
    eff = (day_n - 1) + _intra_frac(h, cur_date.weekday())
    pc = _pace_cum(eff, pac)
    final_pace = cum / pc if pc else None
    final_model = _m.exp(a + b * _m.log(open_ad)) if (a and b and open_ad) else None
    ests = [x for x in (final_pace, final_model) if x]
    if not ests:
        return None
    central = sum(ests) / len(ests)
    # 감쇠 보정: 이튿날/첫날 비율이 comp(0.73)보다 빠르면 하단으로
    # 일별 실측(회원 스냅샷 날짜별 최대값)으로 감쇠 신호 — report_state보다 최신·견고
    mdf = {}
    try:
        for r in csv.DictReader(open(MEMBER_SNAP, encoding="utf-8-sig")):
            dd = r.get("날짜"); a = _num(r.get("관객수"))
            if dd:
                mdf[dd] = max(mdf.get(dd, 0), a or 0)
    except Exception:
        pass
    lean = ""
    d1 = mdf.get(OPEN_DATE.strftime("%Y-%m-%d")) or open_ad
    completes = sorted(d for d in mdf if d < cur_date.strftime("%Y-%m-%d"))
    d2 = mdf.get(completes[1]) if len(completes) >= 2 else None
    if not d2 and day_n == 2:               # 오늘이 이튿날이면 나우캐스트로 대체
        ef = _eod_member_forecast()
        if ef:
            d2 = ef.get("pred")
    if d1 and d2:
        ratio = d2 / d1
        if ratio < 0.6:
            central = min(ests) * 0.90       # 빠른 감쇠 → 보수적(하단)
            lean = f"이튿날/첫날 {ratio:.2f}로 comp(0.73)보다 빨라 하단 반영"
    lo = int(round(central * 0.8 / 1000) * 1000)
    hi = int(round(central * 1.35 / 1000) * 1000)
    # 주말 선예매(최신 스냅샷)
    wk = {}
    try:
        fa = json.load(io.open(os.path.join(BASE, "future_advance_log.json"), encoding="utf-8"))
        for tgt in ("2026-09-05", "2026-09-06", "2026-09-07"):
            snaps_t = fa.get(tgt, {})
            if snaps_t:
                latest = sorted(snaps_t.items())[-1][1]
                wk[tgt] = latest.get("aud")
    except Exception:
        pass
    return {"central": int(round(central / 100) * 100), "lo": lo, "hi": hi,
            "cum": cum, "day_n": day_n, "final_pace": int(final_pace) if final_pace else None,
            "final_model": int(final_model) if final_model else None, "lean": lean, "weekend": wk}


def _final_card():
    f = _final_forecast()
    if not f:
        return ""
    wk = f.get("weekend") or {}
    wkstr = ""
    if wk:
        names = {"2026-09-05": "금", "2026-09-06": "토", "2026-09-07": "일"}
        wkstr = " · ".join(f"{names[k]} {v:,}" for k, v in wk.items() if v)
    parts = []
    if f["final_pace"]:
        parts.append(f"{f['day_n']}일차 누적 {f['cum']:,} ÷ 페이싱 → {f['final_pace']/10000:.1f}만")
    if f["final_model"]:
        parts.append(f"개봉일 모델 {f['final_model']/10000:.1f}만")
    sub = " · ".join(parts)
    lean = f' · {f["lean"]}' if f.get("lean") else ""
    wkline = (f'<div class="ffwk">주말 선예매(계속 유입): {wkstr}</div>' if wkstr else "")
    return (f'<div class="ff"><div class="ffh">🏁 생애 최종 관객 예측 <span>진행 중 · {f["day_n"]}일차</span></div>'
            f'<div class="ffv">약 {f["central"]:,}<small>명 ({f["lo"]:,}~{f["hi"]:,})</small></div>'
            f'<div class="ffn">{sub}{lean}</div>{wkline}'
            f'<div class="ffn2">아직 개봉 초반이라 구간이 넓습니다. 3일차·첫 주말이 확정되면 급격히 좁혀집니다.</div></div>')


def _member_delta_section():
    """오늘 실관객 시간대별 증가(회원통계 수집 간격) 막대 — '몇명씩 늘었나' 가시화."""
    if not os.path.exists(MEMBER_SNAP):
        return ""
    try:
        rows = [r for r in csv.DictReader(open(MEMBER_SNAP, encoding="utf-8-sig")) if r.get("관객수")]
    except Exception:
        return ""
    byday = {}
    for r in rows:
        d = r.get("날짜")
        if d:
            byday.setdefault(d, []).append((r.get("수집시각", "")[11:16], _num(r.get("관객수")) or 0))
    if not byday:
        return ""
    day = sorted(byday)[-1]
    ser = [p for p in byday[day] if p[0]]
    # 시(hour) 단위로 압축: 같은 시각대 마지막값
    comp = {}
    for t, v in ser:
        comp[t[:2]] = (t, v)
    ser = [comp[k] for k in sorted(comp)]
    if len(ser) < 2:
        return ""
    deltas = [(ser[i][0], ser[i][1] - ser[i - 1][1], ser[i][1]) for i in range(1, len(ser))]
    n = len(deltas)
    W, H, PT, PB = 680, 150, 22, 30
    dmax = max((d for _, d, _c in deltas), default=1)
    hi = max(dmax, 1)
    plot_h = H - PT - PB
    bw = (W - 12) / n
    parts = [f'<line x1="6" x2="{W-6}" y1="{H-PB:.1f}" y2="{H-PB:.1f}" stroke="var(--line)" stroke-width="1"/>']
    for i, (t, d, cum_i) in enumerate(deltas):
        cx = 6 + i * bw
        bh = max(abs(d) / hi * plot_h, 0.8)
        by = H - PB - bh
        col = "#7ee0a8" if d >= 0 else "#e06a6a"
        parts.append(f'<rect x="{cx + bw*0.16:.1f}" y="{by:.1f}" width="{bw*0.68:.1f}" height="{bh:.1f}" '
                     f'rx="1.5" fill="{col}"><title>{day} {t} · +{d:,} · 누적 {cum_i:,}</title></rect>')
        mid = cx + bw / 2
        parts.append(f'<text x="{mid:.1f}" y="{by-3:.1f}" text-anchor="middle" fill="var(--ink)" '
                     f'font-size="10.5" font-weight="700">{d:+,}</text>')
        parts.append(f'<text x="{mid:.1f}" y="{H-16:.1f}" text-anchor="middle" fill="var(--muted)" '
                     f'font-size="9.5" font-weight="600">{cum_i:,}</text>')
        parts.append(f'<text x="{mid:.1f}" y="{H-4:.1f}" text-anchor="middle" fill="var(--muted)" '
                     f'font-size="9">{t}</text>')
    svg = (f'<svg viewBox="0 0 {W} {H}" width="100%" style="display:block;height:auto;overflow:visible">'
           f'{"".join(parts)}</svg>')
    return (f'<div class="panel"><h2>오늘({day[5:]}) 실관객 시간대별 증가 (막대=시간당 유입 · 아래=그 시점 누적)</h2>{svg}'
            f'<div class="empty" style="padding:8px 0 0;text-align:left">회원통계 수집 간격의 실관객 순유입입니다. '
            f'낮·저녁 유입 패턴을 보고 아래 \'오늘 예상 마감\'과 함께 읽으면 흐름이 잡힙니다.</div></div>')


def _eod_member_forecast():
    """회원통계 실관객 + 개봉일 시간대 누적 프로파일로 '오늘 마감 실관람' 역산.
    하루가 진행될수록(프로파일→1.0) 예측이 현재값에 수렴해 자동으로 좁혀진다."""
    s = _member_summary()
    if not s:
        return None
    aud = s.get("관객수") or 0
    if aud < 200:
        return None
    # 수집 시각(시)
    dow = None
    try:
        snaps = list(csv.DictReader(open(MEMBER_SNAP, encoding="utf-8-sig")))
        ts = snaps[-1].get("수집시각", "")
        dt = datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        h = dt.hour + dt.minute / 60.0
        dow = dt.weekday()
    except Exception:
        h = datetime.datetime.now().hour + 0.0
    # 시각→그날 실관객 누적 비중(요일보정: 금~일은 주말 곡선). 저녁으로 갈수록 실측에 수렴.
    f = _intra_frac(h, dow)
    hw = 0.05 * (1 - f) + 0.01          # 오전은 넓게, 저녁으로 갈수록 촘촘하게
    pred = aud / f
    lo = aud / min(1.0, f + hw)
    hi = aud / max(0.32, f - hw)
    r100 = lambda n: int(round(n / 100.0) * 100)
    wk = "주말곡선" if (dow is not None and dow >= 4) else "평일곡선"
    return {"pred": r100(pred), "lo": r100(lo), "hi": r100(hi), "wk": wk,
            "aud": aud, "hm": f"{int(h):02d}:{int((h%1)*60):02d}", "frac": f}


def _eod_member_card():
    f = _eod_member_forecast()
    if not f:
        return ""
    cmp = ""
    cf = _comp_forward()
    if cf and cf.get("pace", 0) > 0:
        gap = (f["pred"] - cf["pace"]) / cf["pace"] * 100
        if gap <= -12:
            tag = f'실측이 {abs(gap):.0f}% 낮음 → <b>예상보다 빠른 소진</b>(즉시소진 강함)'
        elif gap >= 12:
            tag = f'실측이 {gap:.0f}% 높음 → 예상보다 견조'
        else:
            tag = '근거 예측과 대체로 일치'
        cmp = (f'<div class="eodcmp">📐 근거 예측 <b>{cf["pace"]:,}명</b>'
               f'<small>(comp 페이싱·모델)</small> vs 실측 나우캐스트 {f["pred"]:,}명 — {tag}</div>')
    return (f'<div class="eodm"><div class="eodh">🎯 오늘 예상 마감 관객 (실관람)<span>{f["hm"]} 기준</span></div>'
            f'<div class="eodv">약 {f["pred"]:,}<small>명 ({f["lo"]:,}~{f["hi"]:,})</small></div>'
            f'<div class="eodn">현재 실관객 {f["aud"]:,} · 그린랜드2 {f.get("wk","")} 역산(현재 {f["frac"]*100:.0f}% 지점, 요일보정)</div>'
            f'{cmp}</div>')


def _eod_forecast():
    """오늘 마감(23:59) 예매관객 역산 — 최근 완주일들의 '현재 시각까지 붙는 비율'로 오늘 총증가 추정."""
    import statistics as _st
    from collections import defaultdict
    rows = _rows()
    series = [(r[0], _num(r[7]) or 0) for r in rows if len(r) > 7 and _num(r[7]) is not None]
    if len(series) < 4:
        return None
    day = defaultdict(list)
    for ts, b in series:
        day[ts[:10]].append((ts[11:16], b))
    days = sorted(day)
    if len(days) < 2:
        return None
    today = days[-1]
    now_hm = day[today][-1][0]
    tstart = day[today][0][1]
    now = day[today][-1][1]
    add_so_far = now - tstart
    fracs = []
    for d in days[:-1]:                       # 완주일(어제까지)
        s = day[d]
        full = s[-1][1] - s[0][1]
        if full <= 0:
            continue
        byn = s[0][1]
        for t, b in s:
            if t <= now_hm:
                byn = b
        fr = (byn - s[0][1]) / full
        if 0.02 <= fr <= 1.0:
            fracs.append(fr)
    if not fracs or add_so_far <= 0:
        return None
    frm = _st.median(fracs)
    eod = tstart + add_so_far / frm
    lo = tstart + add_so_far / max(fracs)     # 높은 비율일수록 낮은 예측
    hi = tstart + add_so_far / min(fracs)
    return {"eod": int(round(eod)), "lo": int(round(lo)), "hi": int(round(hi)),
            "cur": now, "add": add_so_far, "now_hm": now_hm, "n": len(fracs)}


def _eod_card():
    f = _eod_forecast()
    if not f:
        return ""
    org = f["eod"] - PROMO_BASE
    sub = (f'현재 {f["cur"]:,} · 오늘 +{f["add"]:,} · 최근 {f["n"]}일 시간대 패턴 역산'
           + (f' · 실예매 ~{org:,}' if SHOW_ORGANIC else ''))
    return (f'<div class="eod"><div class="eodh">📈 오늘 마감 예매 예측<span>{f["now_hm"]} 기준</span></div>'
            f'<div class="eodv">약 {f["eod"]:,}<small>명 ({f["lo"]:,}~{f["hi"]:,})</small></div>'
            f'<div class="eodn">{sub}</div></div>')


def _hero_grid(book, organic, rate, rank):
    """상단 히어로 그리드 — 개봉 후엔 실관객, 개봉 전엔 예매 기준."""
    s = _member_summary()
    post = bool(s and (s.get("누적관객수") or 0) > 0 and datetime.date.today() >= OPEN_DATE)
    if post:
        cum = s.get("누적관객수") or 0
        today_a = s.get("관객수") or 0
        scr = s.get("스크린수") or 0
        shows = s.get("상영횟수") or 0
        return ('<div class="grid">'
                '<div class="card hero"><div class="k">누적 실관객 (회원통계)</div>'
                f'<div class="v">{cum:,}</div>'
                f'<div class="note">오늘 {today_a:,}명 · 개봉일부터 누적</div></div>'
                f'<div class="card"><div class="k">오늘 실관객</div><div class="v">{today_a:,}</div></div>'
                f'<div class="card"><div class="k">오늘 편성</div><div class="v">{scr}'
                f'<small style="font-size:14px;color:var(--muted);font-weight:600">관·{shows}회</small></div></div>'
                '</div>')
    if SHOW_ORGANIC:
        note = (f"이 중 실예매(프로모 {PROMO_BASE:,}장 제외) <b>{organic:,}명</b>" if book else "이 중 실예매 —")
    else:
        note = "KOBIS 실시간 예매 기준 · 개봉일 이전 선예매 포함"
    hero_book = f"{book:,}" if book else "—"
    return ('<div class="grid">'
            '<div class="card hero"><div class="k">예매 관객 (누적)</div>'
            f'<div class="v">{hero_book}</div><div class="note">{note}</div></div>'
            f'<div class="card"><div class="k">예매율</div><div class="v">{rate or "—"}</div></div>'
            f'<div class="card"><div class="k">예매 순위</div><div class="v">{(str(rank) + "위") if rank else "—"}</div></div>'
            '</div>')


def generate(csv_path=CSV_PATH, out_path=OUT_PATH):
    load_band()   # 밴드는 매 빌드마다 교환 파일에서 다시 읽는다
    rows = _rows()
    today = datetime.date.today()
    dday = (OPEN_DATE - today).days
    ddtxt = (f"D-{dday}" if dday > 0 else ("개봉일(D-DAY)" if dday == 0 else f"개봉 {-dday + 1}일차"))

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
    html = html.replace("__HEROGRID__", _hero_grid(book, organic, rate, rank))
    html = html.replace("__SPARK__", spark or '<div class="empty">예매 추세는 수집이 몇 시간 쌓이면 표시됩니다</div>')
    html = html.replace("__FINAL__", _final_card())
    html = html.replace("__DAILYREPORT__", _daily_report_card())
    html = html.replace("__MEMBERDELTA__", _member_delta_section())
    html = html.replace("__EODMEMBER__", _eod_member_card())
    html = html.replace("__EODCARD__", _eod_card())
    html = html.replace("__MEMBER__", _member_section())
    html = html.replace("__REGIONMAP__", _region_map())
    html = html.replace("__DAILYTREND__", _daily_trend_section())
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
  .cbox{position:relative;height:210px;width:100%}
  .band{display:flex;align-items:center;gap:10px;margin-top:8px;font-size:13px}
  .bar{flex:1;height:8px;border-radius:99px;background:linear-gradient(90deg,#3a4260,#8b9dff);position:relative}
  .foot{text-align:center;color:var(--muted);font-size:11.5px;margin-top:22px;line-height:1.7}
  .dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--good);margin-right:6px;
    box-shadow:0 0 0 0 rgba(74,222,128,.5);animation:b 2.4s infinite}
  @keyframes b{70%{box-shadow:0 0 0 7px rgba(74,222,128,0)}100%{box-shadow:0 0 0 0 rgba(74,222,128,0)}}
  .mstat{background:linear-gradient(135deg,#241d2e 0%,#171b24 78%);border:1px solid #4a3a5e;
    border-radius:16px;padding:16px 20px;margin-top:12px}
  .mstat .mh{font-weight:750;font-size:13px;color:#d6b8ff;display:flex;justify-content:space-between;
    align-items:baseline;margin-bottom:12px}
  .mstat .mh span{font-size:11px;color:var(--muted);font-weight:400}
  .mgrid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;text-align:center}
  .mgrid b{display:block;font-size:24px;font-weight:850;letter-spacing:-.02em;color:#e7d6ff;
    font-variant-numeric:tabular-nums}
  .mgrid span{font-size:11px;color:var(--muted)}
  .mstat .mnote{font-size:12px;color:var(--muted);margin-top:10px;text-align:center}
  .trow{display:flex;align-items:center;gap:9px;margin:6px 0;font-size:13px}
  .trow .tn{width:120px;flex:none;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .trow .tb{flex:1;height:9px;border-radius:99px;background:#20242e;overflow:hidden}
  .trow .tb i{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,#5f7bff,#aab6ff)}
  .trow .tv{width:78px;flex:none;text-align:right;font-variant-numeric:tabular-nums}
  .trow .tv em{color:var(--muted);font-style:normal;font-size:10.5px;margin-left:4px}
  .heat{display:grid;gap:3px;overflow-x:auto}
  .hcell{min-width:30px;height:26px;display:flex;align-items:center;justify-content:center;
    font-size:10.5px;border-radius:5px;background:#181c26;font-variant-numeric:tabular-nums;color:#dfe4ef}
  .hcell.hh{background:transparent;color:var(--muted);font-size:10px;height:20px}
  .hcell.hn{justify-content:flex-start;background:transparent;color:var(--ink);font-size:11.5px;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding-right:4px}
  .hrow{display:contents}
  .hrow.tot .hcell{outline:1px solid rgba(139,157,255,.35)}
  .hleg{font-size:11px;color:var(--muted);margin-top:8px}
  .rc{display:grid;grid-template-columns:1fr 1fr;gap:18px}
  @media(max-width:520px){.mgrid{grid-template-columns:repeat(2,1fr)}.rc{grid-template-columns:1fr}}
  .ff{background:linear-gradient(135deg,#0f2a2e 0%,#171b24 76%);border:1px solid #2b5a5f;
    border-radius:16px;padding:18px 20px;margin-top:12px}
  .ff .ffh{font-weight:800;font-size:14px;color:#8fe3d6;display:flex;justify-content:space-between;
    align-items:baseline;margin-bottom:6px}
  .ff .ffh span{font-size:11px;color:var(--muted);font-weight:400}
  .ff .ffv{font-size:40px;font-weight:850;letter-spacing:-.02em;color:#b6f0e4;font-variant-numeric:tabular-nums}
  .ff .ffv small{font-size:15px;font-weight:600;color:var(--muted)}
  .ff .ffn{font-size:12.5px;color:var(--ink);margin-top:6px;line-height:1.6}
  .ff .ffwk{font-size:12.5px;color:#8fe3d6;margin-top:6px}
  .ff .ffn2{font-size:11.5px;color:var(--muted);margin-top:8px;padding-top:8px;border-top:1px solid rgba(143,227,214,.2)}
  .drep{background:linear-gradient(135deg,#141b2c 0%,#171b24 80%);border:1px solid #2c3a55;
    border-radius:16px;padding:16px 20px;margin-top:12px}
  .drep summary.dh{font-weight:800;font-size:14px;color:#cdd6ff;display:flex;justify-content:space-between;
    align-items:baseline;gap:10px;line-height:1.4;cursor:pointer;list-style:none}
  .drep summary.dh::-webkit-details-marker{display:none}
  .drep summary.dh span{font-size:11px;color:var(--muted);font-weight:400;white-space:nowrap}
  .drep[open] summary.dh{margin-bottom:8px}
  .drep p{font-size:13.5px;line-height:1.75;margin:.5em 0;color:var(--ink)}
  .drep p b{color:#aab6ff}
  .eodm{background:linear-gradient(135deg,#3a2a0e 0%,#171b24 74%);border:1px solid #6a5320;
    border-radius:16px;padding:16px 20px;margin-top:12px}
  .eodm .eodh{font-weight:750;font-size:13px;color:#f4c89a;display:flex;justify-content:space-between;
    align-items:baseline;margin-bottom:6px}
  .eodm .eodh span{font-size:11px;color:var(--muted);font-weight:400}
  .eodm .eodv{font-size:36px;font-weight:850;letter-spacing:-.02em;color:#f7d9b0;font-variant-numeric:tabular-nums}
  .eodm .eodv small{font-size:14px;font-weight:600;color:var(--muted)}
  .eodm .eodn{font-size:12px;color:var(--muted);margin-top:5px}
  .eodm .eodcmp{font-size:12px;color:var(--ink);margin-top:8px;padding-top:8px;
    border-top:1px solid rgba(244,200,154,.22);line-height:1.6}
  .eodm .eodcmp b{color:#f4c89a}
  .eodm .eodcmp small{color:var(--muted);font-size:10.5px}
  .eod{background:linear-gradient(135deg,#152a20 0%,#171b24 78%);border:1px solid #2f5b45;
    border-radius:16px;padding:16px 20px;margin-top:12px}
  .eod .eodh{font-weight:750;font-size:13px;color:#7ee0a8;display:flex;justify-content:space-between;
    align-items:baseline;margin-bottom:6px}
  .eod .eodh span{font-size:11px;color:var(--muted);font-weight:400}
  .eod .eodv{font-size:34px;font-weight:850;letter-spacing:-.02em;color:#a8f0c6;font-variant-numeric:tabular-nums}
  .eod .eodv small{font-size:14px;font-weight:600;color:var(--muted)}
  .eod .eodn{font-size:12px;color:var(--muted);margin-top:5px}
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

  __HEROGRID__

  __FINAL__

  __DAILYREPORT__

  __MEMBERDELTA__

  __EODMEMBER__

  __EODCARD__

  __COMMENT__

  __MEMBER__

  __DAILYTREND__

  __REGIONMAP__

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
