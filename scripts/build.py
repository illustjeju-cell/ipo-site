# -*- coding: utf-8 -*-
"""공모주 나침반 빌드 — data/ipos.json 을 정적 사이트로 만든다."""
import json, os, re, html, shutil, datetime, math

try:
    from PIL import Image, ImageDraw, ImageFont
    _FONT_DIR = "/usr/share/fonts/opentype/noto"
    FONT_B = f"{_FONT_DIR}/NotoSansCJK-Bold.ttc" if os.path.exists(f"{_FONT_DIR}/NotoSansCJK-Bold.ttc") else None
    FONT_R = f"{_FONT_DIR}/NotoSansCJK-Regular.ttc" if os.path.exists(f"{_FONT_DIR}/NotoSansCJK-Regular.ttc") else None
    HAS_PIL = bool(FONT_B and FONT_R)
except Exception:
    HAS_PIL = False

SITE_URL = os.environ.get("SITE_URL", "https://ipo.acoustic42.com").rstrip("/")
ADSENSE = os.environ.get("ADSENSE_CLIENT", "")
CNAME = os.environ.get("CNAME", "")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def esc(s): return html.escape(str(s or ""), quote=True)
def won(v): return f"{v:,}원" if isinstance(v, int) else "-"

CSS = open(os.path.join(ROOT, "templates", "style.css"), encoding="utf-8").read() if os.path.exists(os.path.join(ROOT, "templates", "style.css")) else ""

def dday(iso, today):
    if not iso: return ""
    d = (datetime.date.fromisoformat(iso) - today).days
    return "오늘" if d == 0 else f"D-{d}" if d > 0 else "종료"

def head(title, desc, url, body_cls="", img=""):
    ads = f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE}" crossorigin="anonymous"></script>' if ADSENSE else ""
    ogimg = f"""
<meta property="og:image" content="{img}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">""" if img else ""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website"><meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{url}">{ogimg}
{ads}<style>{CSS}</style></head>
<body class="{body_cls}"><header class="site"><a href="/">공모주 나침반</a><nav><a href="/calculator.html">🧮 증거금 계산기</a> <a href="/calendar.html">📅 일정 캘린더</a></nav></header><main>"""

FOOT = """</main><footer>공모 일정과 공모가는 금융감독원 전자공시시스템(DART) 공시를 바탕으로 정리합니다. 투자 판단의 책임은 본인에게 있습니다.</footer></body></html>"""

# 디스플레이 광고 슬롯 — 광고 단위 코드(숫자)가 오면 AD_SLOTS에 채운다. 비어 있으면 렌더링하지 않는다.
AD_SLOTS = {
    "detail-top": "7760079595",
    "detail-bottom": "7760079595",
}

def ad(name):
    slot = (AD_SLOTS.get(name) or "").strip()
    if not slot or not ADSENSE:
        return ""
    return (f'<div class="adslot" style="margin:16px 0">'
            f'<ins class="adsbygoogle" style="display:block" data-ad-client="{ADSENSE}" '
            f'data-ad-slot="{slot}" data-ad-format="auto" data-full-width-responsive="true"></ins>'
            f'<script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script></div>')

def price_line(x):
    if x.get("price_final"): return f"확정공모가 {won(x['price_final'])}"
    if x.get("price_low") and x.get("price_high"): return f"희망공모가 {won(x['price_low'])} ~ {won(x['price_high'])}"
    return "공모가 미정"

def demand_score(x):
    """수요예측 지표 점수 — 공시에서 확인되는 지표만으로 계산하는 참고 수치.
    구성: 기관 경쟁률(0.5) · 의무보유확약 비율(0.25) · 공모가의 희망밴드 내 위치(0.25).
    핵심 지표인 경쟁률이 없으면 점수를 만들지 않는다 — 공모가 위치만으로는 수요를 판단할 수 없어
    '밴드 상단 확정 = 100점' 같은 오해를 부른다 (2026-11-10 로컬 검수에서 확인).
    종목 추천이 아니라 기관 수요 지표의 정리다."""
    if not x.get("demand_ratio"): return None
    parts = []
    if x.get("demand_ratio"):
        frac = min(1.0, math.log10(max(x["demand_ratio"], 1.0)) / math.log10(3000.0))
        parts.append(("수요예측 경쟁률", f"{x['demand_ratio']:,} : 1", frac, 0.5))
    if x.get("lockup_pct"):
        frac = min(1.0, x["lockup_pct"] / 40.0)
        parts.append(("의무보유확약 비율", f"{x['lockup_pct']}%", frac, 0.25))
    if x.get("price_final") and x.get("price_low") and x.get("price_high") and x["price_high"] > x["price_low"]:
        pos = (x["price_final"] - x["price_low"]) / (x["price_high"] - x["price_low"])
        pos = max(0.0, min(1.0, pos))
        where = "밴드 상단" if pos >= 0.99 else "밴드 하단" if pos <= 0.01 else f"밴드 내 {pos * 100:.0f}% 위치"
        parts.append(("확정가의 위치", where, pos, 0.25))
    if not parts: return None
    wsum = sum(p[3] for p in parts)
    score = round(100 * sum(p[2] * p[3] for p in parts) / wsum)
    grade = "기관 수요 강함" if score >= 70 else "기관 수요 보통" if score >= 40 else "기관 수요 약함"
    return score, grade, parts

def score_box(x):
    s = demand_score(x)
    if not s: return ""
    score, grade, parts = s
    bars = "".join(
        f"""<div class="srow"><span class="slab">{esc(lab)}</span><span class="sbar"><i style="width:{frac * 100:.0f}%"></i></span><span class="sval">{esc(val)}</span></div>"""
        for lab, val, frac, _w in parts)
    lack = "<p class='snote'>지표가 부족해 참고용으로만 보세요.</p>" if len(parts) < 2 else ""
    return f"""<section class="score"><div class="shead"><span class="snum">{score}</span><span class="sgrade">{esc(grade)}</span></div>
{bars}{lack}<p class="snote">공시 지표(경쟁률·확약·공모가 위치)로 계산한 참고 수치입니다. 투자 권유가 아닙니다.</p></section>"""

def card(x, today):
    sub = ""
    if x.get("sub_start"):
        sub = f"청약 {x['sub_start']} ~ {x.get('sub_end') or x['sub_start']} <b>{dday(x['sub_start'], today)}</b>"
    s = demand_score(x)
    badge = f"<div class='cscore'>수요예측 지표 <b>{s[0]}점</b> · {esc(s[1])}</div>" if s and len(s[2]) >= 2 else ""
    return f"""<a class="card" href="/i/{x['corp_code']}.html">
<div class="cname">{esc(x['corp_name'])} <span class="stage">{esc(x['stage'])}</span></div>
<div class="cprice">{esc(price_line(x))}</div>
<div class="cmeta">{sub}</div>
<div class="cmeta">{esc(x.get('underwriter') or '')}</div>{badge}</a>"""

def mdd(iso):
    if not iso: return ""
    d = datetime.date.fromisoformat(iso)
    return f"{d.month}월 {d.day}일"

def _card_img(path, name, main, sub):
    """링크 미리보기(OG)용 카드 이미지 1200x630 생성. 실패하면 False (빌드는 계속)."""
    if not HAS_PIL: return False
    try:
        W, H = 1200, 630
        NAVY, BLACK, GRAY = (18, 58, 109), (17, 17, 17), (110, 110, 110)
        img = Image.new("RGB", (W, H), (255, 255, 255))
        d = ImageDraw.Draw(img)
        def fit(text, fp, size, min_size=30):
            while size > min_size:
                f = ImageFont.truetype(fp, size)
                if d.textbbox((0, 0), text, font=f)[2] <= 1080: return f
                size -= 4
            return ImageFont.truetype(fp, min_size)
        def center(text, y, f, fill):
            b = d.textbbox((0, 0), text, font=f)
            d.text(((W - (b[2] - b[0])) / 2 - b[0], y), text, font=f, fill=fill)
        d.rectangle([0, 0, W, 84], fill=NAVY)
        center("공모주 나침반", 22, ImageFont.truetype(FONT_B, 38), (255, 255, 255))
        center(name, 150, fit(name, FONT_B, 76), NAVY)
        center(main, 262, fit(main, FONT_B, 96), BLACK)
        d.line([300, 440, 900, 440], fill=(200, 208, 220), width=3)
        center(sub, 472, fit(sub, FONT_R, 44, 26), GRAY)
        d.rectangle([0, H - 26, W, H], fill=NAVY)
        img.save(path, optimize=True)
        return True
    except Exception:
        return False

def og_card(path, x, today):
    bits = []
    if x.get("sub_start"):
        bits.append(f"청약 {mdd(x['sub_start'])} ~ {mdd(x.get('sub_end') or x['sub_start'])}")
    elif x.get("listing_date"):
        bits.append(f"상장 {mdd(x['listing_date'])}")
    s = demand_score(x)
    if s: bits.append(f"수요예측 지표 {s[0]}점")
    if x.get("underwriter"): bits.append(x["underwriter"])
    return _card_img(path, x["corp_name"], price_line(x), " · ".join(bits))

def detail(x, today, img=""):
    rows = []
    def row(k, v):
        if v: rows.append(f"<tr><th>{k}</th><td>{esc(v)}</td></tr>")
    if x.get("sub_start"): row("청약일", f"{x['sub_start']} ~ {x.get('sub_end') or x['sub_start']} ({dday(x['sub_start'], today)})")
    if x.get("demand_start"): row("수요예측일", f"{x['demand_start']} ~ {x.get('demand_end') or x['demand_start']}")
    if x.get("price_low"): row("희망공모가", f"{won(x['price_low'])} ~ {won(x['price_high'])}")
    if x.get("price_final"): row("확정공모가", won(x["price_final"]))
    if x.get("shares"): row("공모주식수", f"{x['shares']:,}주")
    row("대표주관회사", x.get("underwriter"))
    if x.get("demand_ratio"): row("수요예측 경쟁률", f"{x['demand_ratio']:,} : 1")
    if x.get("lockup_pct"): row("의무보유확약", f"{x['lockup_pct']}%")
    if x.get("listing_date"): row("상장예정일", x["listing_date"])
    body = f"""<h1>{esc(x['corp_name'])} 공모주 청약 일정·공모가</h1>
<p class="lead">{esc(price_line(x))} · {esc(x.get('underwriter') or '')}</p>
{score_box(x)}
{ad("detail-top")}
<table class="facts">{"".join(rows)}</table>
<p><a class="calcbtn" href="/calculator.html?price={x.get('price_final') or x.get('price_high') or ''}&name={esc(x['corp_name'])}&ratio={x.get('demand_ratio') or ''}">🧮 이 종목 증거금 계산하기</a></p>
{ics_link(x)}
<p class="src">출처: <a href="{esc(x['dart_url'])}" rel="nofollow">DART 공시 원문</a> ({esc(x['rcept_dt'])} 접수)</p>
{ad("detail-bottom")}"""
    return head(f"{x['corp_name']} 공모주 청약 일정·공모가 | 공모주 나침반",
                f"{x['corp_name']} 공모주 청약 일정, 희망공모가·확정공모가, 수요예측 결과를 정리했습니다.",
                f"{SITE_URL}/i/{x['corp_code']}.html", img=img) + body + FOOT

def calendar_page(items, today):
    ev = {}
    def add(iso, x, t, label):
        if iso: ev.setdefault(iso, []).append({"n": x["corp_name"], "t": t, "l": label, "u": f"/i/{x['corp_code']}.html"})
    for x in items:
        if x.get("sub_start"):
            add(x["sub_start"], x, "sub", "청약 시작" if x.get("sub_end") and x["sub_end"] != x["sub_start"] else "청약")
            if x.get("sub_end") and x["sub_end"] != x["sub_start"]: add(x["sub_end"], x, "sub", "청약 마감")
        if x.get("demand_start"): add(x["demand_start"], x, "dem", "수요예측")
        if x.get("listing_date"): add(x["listing_date"], x, "lst", "상장")
    js = """<script>
var EV = __EVENTS__;
var now = new Date(); var cy = now.getFullYear(), cm = now.getMonth();
var NAMES = {sub: "청약", dem: "수요예측", lst: "상장"};
function pad(n){ return (n < 10 ? "0" : "") + n; }
function render(){
  document.getElementById("cur").textContent = cy + "년 " + (cm + 1) + "월";
  var first = new Date(cy, cm, 1); var startDay = first.getDay();
  var days = new Date(cy, cm + 1, 0).getDate();
  var prevDays = new Date(cy, cm, 0).getDate();
  var html = "<tr><th>일</th><th>월</th><th>화</th><th>수</th><th>목</th><th>금</th><th>토</th></tr>";
  var list = [];
  var cells = [];
  for (var i = 0; i < startDay; i++) cells.push({d: prevDays - startDay + 1 + i, out: 1});
  for (var d = 1; d <= days; d++) cells.push({d: d, out: 0});
  while (cells.length % 7) cells.push({d: cells.length - days - startDay + 1, out: 1});
  for (var r = 0; r < cells.length / 7; r++){
    html += "<tr>";
    for (var c = 0; c < 7; c++){
      var cell = cells[r * 7 + c];
      var iso = cy + "-" + pad(cm + 1) + "-" + pad(cell.d);
      var isToday = !cell.out && iso === now.getFullYear() + "-" + pad(now.getMonth() + 1) + "-" + pad(now.getDate());
      html += "<td class='" + (cell.out ? "out" : "") + (isToday ? " today" : "") + "'><span class='dn'>" + cell.d + "</span>";
      if (!cell.out && EV[iso]) EV[iso].forEach(function(e){
        html += "<a class='ev " + e.t + "' href='" + e.u + "'>" + e.n + " " + e.l + "</a>";
        list.push({iso: iso, e: e});
      });
      html += "</td>";
    }
    html += "</tr>";
  }
  document.getElementById("cal").innerHTML = html;
  list.sort(function(a, b){ return a.iso < b.iso ? -1 : 1; });
  document.getElementById("calist").innerHTML = list.length
    ? list.map(function(it){ return "<li>" + it.iso + " · <a href='" + it.e.u + "'>" + it.e.n + "</a> " + it.e.l + "</li>"; }).join("")
    : "<li>이 달은 일정이 없습니다.</li>";
}
function move(m){ cm += m; if (cm < 0){ cm = 11; cy--; } if (cm > 11){ cm = 0; cy++; } render(); }
render();
</script>"""
    body = f"""<h1>공모주 일정 캘린더</h1>
<p class="legend"><span class="ev sub">청약</span><span class="ev dem">수요예측</span><span class="ev lst">상장</span> 날짜 칩을 누르면 종목 상세로 이동합니다.</p>
<div class="calnav"><button onclick="move(-1)">← 이전 달</button><span class="cur" id="cur"></span><button onclick="move(1)">다음 달 →</button></div>
<table class="cal" id="cal"></table>
<h2 style="font-size:17px;margin-top:20px">이 달의 일정</h2>
<ul class="calist" id="calist"></ul>
""" + js.replace("__EVENTS__", json.dumps(ev, ensure_ascii=False))
    return head("공모주 일정 캘린더 | 공모주 나침반",
                "공모주 청약·수요예측·상장 일정을 한 달 달력으로 확인하세요.",
                SITE_URL + "/calendar.html") + body + FOOT

def ics_link(x):
    if not x.get("sub_start"): return ""
    return f"""<p><a class="icslink" href="/i/{x['corp_code']}.ics" download>📅 청약 일정을 내 캘린더에 저장 (.ics)</a></p>"""

def ics_file(x):
    start = x["sub_start"].replace("-", "")
    end_d = datetime.date.fromisoformat(x.get("sub_end") or x["sub_start"]) + datetime.timedelta(days=1)
    end = end_d.isoformat().replace("-", "")
    desc = f"{price_line(x)} · 주관 {x.get('underwriter') or ''} · {SITE_URL}/i/{x['corp_code']}.html"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//ipo-compass//KO",
             "BEGIN:VEVENT", f"UID:{x['corp_code']}@ipo.acoustic42.com",
             f"DTSTART;VALUE=DATE:{start}", f"DTEND;VALUE=DATE:{end}",
             f"SUMMARY:{x['corp_name']} 공모주 청약", f"DESCRIPTION:{desc}",
             "END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"

def calculator_page(items, today):
    presets = []
    for x in items:
        price = x.get("price_final") or x.get("price_high")
        if not price: continue
        presets.append({"n": x["corp_name"], "p": price,
                        "r": x.get("demand_ratio"),
                        "s": x.get("sub_start") or "9999"})
    presets.sort(key=lambda z: z["s"])
    chips = "".join(
        f"""<button type="button" class="chip" onclick="preset({z['p']}, '{esc(z['n'])}', {z['r'] if z['r'] else 'null'})">{esc(z['n'])}</button>"""
        for z in presets[:14])
    js = """<script>
function fmt(n){ return Math.round(n).toLocaleString("ko-KR"); }
function preset(p, n, r){
  document.getElementById("price").value = p;
  document.getElementById("cname").textContent = n ? (n + " 기준") : "";
  if (r) document.getElementById("ratio").value = r;
  calc();
}
function calc(){
  var price = parseFloat(document.getElementById("price").value) || 0;
  var qty = parseFloat(document.getElementById("qty").value) || 0;
  var rate = parseFloat(document.getElementById("rate").value) || 0.5;
  var ratio = parseFloat(document.getElementById("ratio").value) || 0;
  var margin = price * qty * rate;
  var out = "<div class='rrow'><span>필요 증거금</span><b>" + fmt(margin) + "원</b></div>";
  out += "<div class='rrow'><span>청약 금액 (전액)</span><b>" + fmt(price * qty) + "원</b></div>";
  out += "<div class='rrow'><span>최소 청약 (10주) 증거금</span><b>" + fmt(price * 10 * rate) + "원</b></div>";
  if (ratio > 0 && qty > 0) {
    var est = qty / ratio;
    out += "<div class='rrow'><span>비례 예상 배정</span><b>약 " + (est < 1 ? est.toFixed(2) : fmt(est)) + "주</b></div>";
    out += "<p class='snote'>예상 배정은 청약 주식수 ÷ 경쟁률의 단순 계산입니다. 실제 배정은 균등·비례 방식과 청약 건수에 따라 달라집니다.</p>";
  }
  document.getElementById("result").innerHTML = out;
}
var q = new URLSearchParams(location.search);
if (q.get("price")) {
  document.getElementById("price").value = q.get("price");
  if (q.get("name")) document.getElementById("cname").textContent = q.get("name") + " 기준";
  if (q.get("ratio")) document.getElementById("ratio").value = q.get("ratio");
}
["price", "qty", "rate", "ratio"].forEach(function(id){ document.getElementById(id).addEventListener("input", calc); });
calc();
</script>"""
    body = f"""<h1>공모주 증거금 계산기</h1>
<p class="lead">공모가와 청약 주식수를 넣으면 필요한 증거금을 계산합니다. <span id="cname"></span></p>
<div class="calc">
<label>공모가 (원)<input type="number" id="price" min="0" step="100" placeholder="예: 17600"></label>
<label>청약 주식수 (주)<input type="number" id="qty" min="0" step="10" value="100"></label>
<label>증거금률
<select id="rate"><option value="0.5" selected>50% (일반적)</option><option value="1">100%</option></select></label>
<label>예상 경쟁률 (선택, 비례 배정 추정용)<input type="number" id="ratio" min="0" step="0.01" placeholder="예: 871.74"></label>
<div id="result" class="result"></div>
</div>
<h2 style="font-size:17px">종목으로 바로 계산</h2>
<div class="chips">{chips}</div>
<p class="snote">종목을 누르면 그 종목의 공모가(확정가, 없으면 희망가 상단)와 수요예측 경쟁률이 자동으로 들어갑니다. 증거금률은 종목·증권사 공고에 따라 다를 수 있으니 청약 전 공고에서 확인하세요.</p>
""" + js
    return head("공모주 증거금 계산기 | 공모주 나침반",
                "공모주 청약에 필요한 증거금을 공모가·주식수·경쟁률로 계산하세요.",
                SITE_URL + "/calculator.html") + body + FOOT

def main():
    data = json.load(open(os.path.join(ROOT, "data", "ipos.json"), encoding="utf-8"))
    items = data["items"]
    today = datetime.date.today()
    dist = os.path.join(ROOT, "dist")
    shutil.rmtree(dist, ignore_errors=True)
    os.makedirs(os.path.join(dist, "i"))
    os.makedirs(os.path.join(dist, "cards"))
    default_img = f"{SITE_URL}/cards/default.png" if _card_img(os.path.join(dist, "cards", "default.png"), "공모주 나침반", "청약 일정 한눈에", "공모가·수요예측 점수까지 정리") else ""
    cards = "\n".join(card(x, today) for x in items)
    home = head("공모주 나침반 | 공모주 청약 일정·공모가·수요예측",
                "다가오는 공모주 청약 일정과 공모가, 수요예측 결과를 DART 공시 기준으로 정리합니다.",
                SITE_URL + "/", img=default_img) + f"<h1>공모주 청약 일정</h1><p class='upd'>업데이트 {esc(data['updated'][:16].replace('T', ' '))} · {len(items)}개 종목</p><div class='grid'>{cards}</div>" + FOOT
    open(os.path.join(dist, "index.html"), "w", encoding="utf-8").write(home)
    open(os.path.join(dist, "calendar.html"), "w", encoding="utf-8").write(calendar_page(items, today))
    open(os.path.join(dist, "calculator.html"), "w", encoding="utf-8").write(calculator_page(items, today))
    for x in items:
        cimg = f"{SITE_URL}/cards/{x['corp_code']}.png" if og_card(os.path.join(dist, "cards", x["corp_code"] + ".png"), x, today) else ""
        open(os.path.join(dist, "i", x["corp_code"] + ".html"), "w", encoding="utf-8").write(detail(x, today, cimg))
        if x.get("sub_start"):
            open(os.path.join(dist, "i", x["corp_code"] + ".ics"), "w", encoding="utf-8", newline="").write(ics_file(x))
    dbg = ["<h1>parse debug</h1>"]
    for x in items:
        dbg.append(f"<h2>{esc(x['corp_name'])} ({esc(x['rcept_no'])}) stage={esc(x['stage'])} err={esc(x.get('error'))}</h2>")
        dbg.append("<pre>" + esc(json.dumps({k: v for k, v in x.items() if k not in ("debug",)}, ensure_ascii=False, indent=1)) + "</pre>")
        for k, v in (x.get("debug") or {}).items():
            dbg.append(f"<h3>{esc(k)}</h3><pre>{esc(v)}</pre>")
    open(os.path.join(dist, "debug.html"), "w", encoding="utf-8").write(head("debug", "", SITE_URL + "/debug.html") + "\n".join(dbg) + FOOT)
    if CNAME: open(os.path.join(dist, "CNAME"), "w").write(CNAME + "\n")
    print("built", len(items))

if __name__ == "__main__":
    main()
