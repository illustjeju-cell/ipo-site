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
GA = os.environ.get("GA_ID", "GT-NSSSWH8S")  # jobs와 같은 GA4 프로퍼티 — 호스트네임으로 구분 (2026-11-15)
CNAME = os.environ.get("CNAME", "")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def esc(s): return html.escape(str(s or ""), quote=True)
def won(v): return f"{v:,}원" if isinstance(v, int) else "-"

CSS = open(os.path.join(ROOT, "templates", "style.css"), encoding="utf-8").read() if os.path.exists(os.path.join(ROOT, "templates", "style.css")) else ""

def dday(iso, today):
    if not iso: return ""
    d = (datetime.date.fromisoformat(iso) - today).days
    return "오늘" if d == 0 else f"D-{d}" if d > 0 else "종료"

def head(title, desc, url, body_cls="", img="", og_title=None, og_desc=None):
    # og_title/og_desc: 링크 카드(Threads 등) 전용 문구 — 검색용 <title>과 분리한다 (2026-11-23).
    # 없으면 title/desc를 그대로 쓴다.
    ogt = og_title or title
    ogd = og_desc or desc
    ads = f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE}" crossorigin="anonymous"></script>' if ADSENSE else ""
    ga = f'<script async src="https://www.googletagmanager.com/gtag/js?id={GA}"></script><script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag("js",new Date());gtag("config","{GA}");</script>' if GA else ""
    ogimg = f"""
<meta property="og:image" content="{img}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">""" if img else ""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="naver-site-verification" content="91aee779d77f133a196ee07d1d94801eba426e0b">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website"><meta property="og:title" content="{esc(ogt)}">
<meta property="og:description" content="{esc(ogd)}"><meta property="og:url" content="{url}">{ogimg}
{ads}{ga}<style>{CSS}</style></head>
<body class="{body_cls}"><header class="site"><a href="/">공모주 나침반</a><nav><a href="/issue.html">📌 오늘의 이슈</a> <a href="/tip.html">💡 주식 꿀팁</a> <a href="/calculator.html">🧮 증거금 계산기</a> <a href="/calendar.html">📅 일정 캘린더</a> <a href="/stock-calendar.html">🗓️ 주식 캘린더</a></nav></header><main>"""

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

# 주관사(증권사) 메인 홈페이지 — 상세 페이지 '공모주 청약 바로가기' 대형 배너용 (2026-11-18).
BROKER_URLS = {
    "한국투자증권": "https://www.truefriend.com",
    "미래에셋증권": "https://securities.miraeasset.com",
    "NH투자증권": "https://www.nhqv.com",
    "삼성증권": "https://www.samsungpop.com",
    "KB증권": "https://www.kbsec.com",
    "하나증권": "https://www.hanaw.com",
    "신한투자증권": "https://www.shinhansec.com",
    "키움증권": "https://www.kiwoom.com",
    "대신증권": "https://www.daishin.com",
    "유진투자증권": "https://www.eugenefn.com",
    "아이비케이투자증권": "https://www.ibks.com",
    "IBK투자증권": "https://www.ibks.com",
    "아이엠증권": "https://www.imfnsec.com",
    "iM증권": "https://www.imfnsec.com",
    "하이투자증권": "https://www.imfnsec.com",
    "유안타증권": "https://www.myasset.com",
    "우리투자증권": "https://www.wooriib.com",
    "SK증권": "https://www.sks.co.kr",
    "신영증권": "https://www.shinyoung.com",
    "한양증권": "https://www.hygood.co.kr",
    "한화투자증권": "https://www.hanwhawm.com",
    "교보증권": "https://www.iprovest.com",
    "현대차증권": "https://www.hmsec.com",
    "BNK투자증권": "https://www.bnkfn.co.kr",
}

def broker_name(x):
    u = (x.get("underwriter") or "").strip()
    if not u: return ""
    return re.split(r"[,·/]", u)[0].strip()

def broker_url(x):
    n = broker_name(x)
    return BROKER_URLS.get(n, "") if n else ""

def action_btns(x):
    """상세 페이지 대형 행동 배너: ① 주관사 공모주 청약 바로가기 ② 이 종목 증거금 계산하기.
    2026-11-18 사용자 지시 — 작은 버튼이 아니라 가운데 큼직한 배너로."""
    btns = []
    bu = broker_url(x)
    if bu:
        btns.append(f'<a href="{bu}" target="_blank" rel="noopener" style="display:block;text-align:center;background:#123a6d;color:#fff;font-size:19px;font-weight:800;padding:18px 14px;border-radius:14px;text-decoration:none">🏦 {esc(broker_name(x))} 공모주 청약 바로가기</a>')
    btns.append(f'<a href="/calculator.html?price={x.get("price_final") or x.get("price_high") or ""}&name={esc(x["corp_name"])}&ratio={x.get("demand_ratio") or ""}" style="display:block;text-align:center;background:#eef3fa;color:#123a6d;font-size:19px;font-weight:800;padding:18px 14px;border-radius:14px;text-decoration:none;border:2px solid #123a6d">🧮 이 종목 증거금 계산하기</a>')
    return '<div style="display:flex;flex-direction:column;gap:10px;margin:18px 0">' + "".join(btns) + "</div>"

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

def detail_og(x, today):
    """종목 상세 링크 카드 문구 (2026-11-23): 짧은 CTA 제목 + 숫자 설명.
    제목은 단계에 따라 — 청약 임박이면 '청약 바로가기', 상장 임박이면 '상장일 확인하기'."""
    name = x["corp_name"]
    t = today.isoformat()
    soon = (today + datetime.timedelta(days=21)).isoformat()
    se, ld = x.get("sub_end"), x.get("listing_date")
    if se and t <= se <= soon:
        ogt = f"{name} 청약 바로가기"
    elif ld and t <= ld <= soon:
        ogt = f"{name} 상장일 확인하기"
    elif se and se >= t:
        ogt = f"{name} 청약 바로가기"
    elif ld and ld >= t:
        ogt = f"{name} 상장일 확인하기"
    else:
        ogt = f"{name} 공모주 확인하기"
    bits = []
    if x.get("sub_start") and se: bits.append(f"청약 {mdd(x['sub_start'])}~{mdd(se)}")
    pl = price_line(x)
    if pl != "공모가 미정": bits.append(pl)
    if x.get("demand_ratio"): bits.append(f"수요예측 경쟁률 {x['demand_ratio']:,} : 1")
    else:
        s = demand_score(x)
        if s: bits.append(f"수요예측 지표 {s[0]}점")
    if ld: bits.append(f"상장 {mdd(ld)}")
    return ogt, " · ".join(bits)

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
{action_btns(x)}
{decision_banner(x, today)}
{ics_link(x)}
<p class="src">출처: <a href="{esc(x['dart_url'])}" rel="nofollow">DART 공시 원문</a> ({esc(x['rcept_dt'])} 접수)</p>
{ad("detail-bottom")}"""
    _ogt, _ogd = detail_og(x, today)
    return head(f"{x['corp_name']} 공모주 청약 일정·공모가 | 공모주 나침반",
                f"{x['corp_name']} 공모주 청약 일정, 희망공모가·확정공모가, 수요예측 결과를 정리했습니다.",
                f"{SITE_URL}/i/{x['corp_code']}.html", img=img, og_title=_ogt, og_desc=_ogd or None) + body + FOOT

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
                SITE_URL + "/calendar.html", og_title="공모주 청약 일정 확인하기") + body + FOOT

# ---------- 주식 일정 캘린더 (2026-11-20 확장: 배당·실적·주총) ----------
STOCK_NAMES = {"dividend": "배당 기준일", "earnings": "실적 발표", "meeting": "주주총회"}
STOCK_CLS = {"dividend": "div", "earnings": "ern", "meeting": "met"}
WD = "월화수목금토일"

def movers_html(market, today):
    """오늘의 상한가·하한가 섹션 + 바로가기 버튼 (2026-11-20 사용자 제안).
    데이터는 collect_market.py가 가격제한폭 도달 여부로 정확히 가려낸 data/market.json."""
    if not market or (not market.get("upper") and not market.get("lower")):
        return "", ""
    mdate = market.get("date") or today.isoformat()
    md = datetime.date.fromisoformat(mdate)
    day_label = "오늘" if mdate == today.isoformat() else f"{md.month}월 {md.day}일"
    def val_fmt(v):
        eok = v / 100.0  # 백만원 → 억원
        return f"{eok / 10000:.1f}조원" if eok >= 10000 else f"{eok:,.0f}억원"
    def rows(items, up):
        if not items:
            return f"<p style='color:#889;font-size:14.5px'>{'상한가' if up else '하한가'} 종목이 없어요.</p>"
        out = []
        for it in items:
            sign = "+" if up else ""
            color = "#c62828" if up else "#1565c0"
            out.append(f"<div class='scrow'><a class='scname' style='text-decoration:none' href='https://finance.naver.com/item/main.naver?code={esc(it['code'])}' target='_blank' rel='nofollow noopener'>{esc(it['name'])}</a>"
                       f"<span class='scmk'>{esc(it['market'])}</span>"
                       f"<span class='scmv'>{it['close']:,}원 <b style='color:{color}'>{sign}{it['ratio']:.2f}%</b> · 거래대금 {val_fmt(it['value'])}</span></div>")
        return "".join(out)
    btns = ('<div style="display:flex;gap:10px;flex-wrap:wrap;margin:14px 0 4px">'
            f'<a href="#upper" style="flex:1 1 200px;display:block;text-align:center;background:#c62828;color:#fff;font-size:17px;font-weight:800;padding:15px 12px;border-radius:14px;text-decoration:none">🔺 {day_label} 상한가 종목 바로가기</a>'
            f'<a href="#lower" style="flex:1 1 200px;display:block;text-align:center;background:#1565c0;color:#fff;font-size:17px;font-weight:800;padding:15px 12px;border-radius:14px;text-decoration:none">🔻 {day_label} 하한가 종목 바로가기</a></div>')
    secs = (f"<h2 class='scmonth' id='upper'>🔺 {md.month}월 {md.day}일 상한가 {len(market.get('upper') or [])}종목</h2>"
            f"<div class='scday'>{rows(market.get('upper') or [], True)}</div>"
            f"<h2 class='scmonth' id='lower'>🔻 {md.month}월 {md.day}일 하한가 {len(market.get('lower') or [])}종목</h2>"
            f"<div class='scday'>{rows(market.get('lower') or [], False)}</div>"
            f"<p style='color:#889;font-size:12.5px'>{esc((market.get('collected_at') or '')[11:16])} 기준 · 네이버 증권 시세로 가격제한폭 도달 종목을 계산했습니다. 장중에는 바뀔 수 있어요.</p>")
    return btns, secs

def stock_calendar_page(events, today, img="", market=None):
    """주식 일정 페이지 — 목록형 (2026-11-20 전면 개편).
    달력 그리드는 모바일에서 칩이 잘리고 빈 칸이 대부분이라 제거했다.
    구조: CTA 배너 → 광고 → 날짜순 일정 목록(날짜 그룹·종목 전체 표시) → 광고 → 최근 실적(접이식) → 하단 CTA."""
    upcoming = sorted((e for e in events if e["type"] in ("dividend", "meeting") and e["date"] >= today.isoformat()),
                      key=lambda e: (e["date"], e["corp_name"]))
    groups = {}
    for e in upcoming: groups.setdefault(e["date"], []).append(e)
    parts = []
    cur_month = None
    for date in sorted(groups):
        d = datetime.date.fromisoformat(date)
        if cur_month != (d.year, d.month):
            cur_month = (d.year, d.month)
            parts.append(f"<h2 class='scmonth'>{d.year}년 {d.month}월</h2>")
        rows = []
        for e in groups[date]:
            if e["type"] == "dividend":
                badge = "<span class='scbadge div'>배당 기준일</span>"
                extra = f"<span class='scdps'>주당 {e['dps']:,}원</span>" if e.get("dps") else ""
            else:
                badge = "<span class='scbadge met'>주주총회</span>"
                extra = ""
            rows.append(f"<div class='scrow'>{badge}<span class='scname'>{esc(e['corp_name'])}</span>{extra}<a class='sclink' href='{esc(e['dart_url'])}' target='_blank' rel='nofollow noopener'>공시 ›</a></div>")
        parts.append(f"<div class='scday'><div class='scdate'><b>{d.month}월 {d.day}일</b> <span>({WD[d.weekday()]})</span> <em>{dday(date, today)}</em></div>{''.join(rows)}</div>")
    uplist = "".join(parts) or "<p>다가오는 일정이 없습니다.</p>"
    lo = (today - datetime.timedelta(days=14)).isoformat()
    recent = [e for e in events if e["type"] == "earnings" and lo <= e["date"] <= today.isoformat()]
    egroups = {}
    for e in recent: egroups.setdefault(e["date"], []).append(e)
    erows = []
    for date in sorted(egroups, reverse=True):
        d = datetime.date.fromisoformat(date)
        chips = "".join(f"<a class='scchip' href='{esc(e['dart_url'])}' target='_blank' rel='nofollow noopener'>{esc(e['corp_name'])}</a>"
                        for e in sorted(egroups[date], key=lambda z: z["corp_name"]))
        erows.append(f"<div class='scerow'><div class='scehead'><b>{d.month}월 {d.day}일</b> <span>{len(egroups[date])}건</span></div><div class='scchips'>{chips}</div></div>")
    earnings_block = (f"<details class='scdet'><summary>최근 실적 발표 {len(recent)}건 펼치기 (최근 14일, 공시 접수일 기준)</summary>{''.join(erows)}</details>"
                      if recent else "<p>최근 14일 안에 실적 발표가 없습니다.</p>")
    cta_top = ('<div style="display:flex;gap:10px;flex-wrap:wrap;margin:16px 0 6px">'
               '<a href="/calendar.html" style="flex:1 1 240px;display:block;text-align:center;background:#123a6d;color:#fff;font-size:18px;font-weight:800;padding:17px 14px;border-radius:14px;text-decoration:none">📅 공모주 청약 일정 보기</a>'
               '<a href="/calculator.html" style="flex:1 1 240px;display:block;text-align:center;background:#eef3fa;color:#123a6d;font-size:18px;font-weight:800;padding:17px 14px;border-radius:14px;text-decoration:none;border:2px solid #123a6d">🧮 공모주 증거금 계산기</a></div>')
    cta_bottom = ('<a href="/" style="display:block;text-align:center;background:#123a6d;color:#fff;font-size:18px;font-weight:800;'
                  'padding:17px 14px;border-radius:14px;text-decoration:none;margin:22px 0 6px">📈 공모주 청약 일정도 확인하세요</a>')
    style = """<style>
.scmonth{font-size:19px;margin:24px 0 10px;color:#123a6d}
.scday{background:#fff;border:1px solid #dde4ee;border-radius:12px;padding:12px 14px;margin:0 0 10px}
.scdate{font-size:15px;margin-bottom:8px;color:#345}
.scdate b{font-size:16.5px;color:#1c2333}
.scdate em{font-style:normal;color:#123a6d;font-weight:800;margin-left:4px}
.scrow{display:flex;align-items:center;gap:8px;padding:7px 0;border-top:1px solid #f0f3f8}
.scrow:first-of-type{border-top:none}
.scbadge{flex:0 0 auto;font-size:11.5px;font-weight:700;border-radius:5px;padding:2.5px 7px}
.scbadge.div{background:#fdf6e0;color:#7a5b00}
.scbadge.met{background:#e6f2f7;color:#0f5b74}
.scname{font-size:16px;font-weight:700;color:#1c2333}
.scdps{font-size:13.5px;color:#7a5b00;font-weight:700}
.sclink{margin-left:auto;flex:0 0 auto;font-size:13.5px;color:#123a6d;text-decoration:none;font-weight:700}
.scdet{background:#fff;border:1px solid #dde4ee;border-radius:12px;padding:12px 14px;margin-top:10px}
.scdet summary{font-size:15.5px;font-weight:700;cursor:pointer;color:#1c2333}
.scerow{padding:10px 0;border-top:1px solid #f0f3f8}
.scehead{font-size:14px;color:#345;margin-bottom:6px}
.scehead span{color:#889;font-size:12.5px}
.scchips{display:flex;flex-wrap:wrap;gap:5px}
.scchip{font-size:12.5px;background:#f2f6fc;color:#345;border-radius:12px;padding:3px 9px;text-decoration:none}
.scmk{flex:0 0 auto;font-size:11px;font-weight:700;background:#eef1f6;color:#667;border-radius:5px;padding:2.5px 6px}
.scmv{margin-left:auto;font-size:13.5px;color:#345;text-align:right}
</style>"""
    movers_btns, movers_secs = movers_html(market, today)
    body = f"""<h1>주식 일정 캘린더</h1>
<p class="lead">배당 기준일과 주주총회 일정을 날짜순으로 정리했습니다. 배당 종목은 주당 배당금까지 표시합니다. (DART 공시 기준)</p>
{movers_btns}
{cta_top}
{ad("detail-top")}
<h2 class="scmonth" style="margin-top:18px">다가오는 배당·주총 일정</h2>
{uplist}
{ad("detail-bottom")}
{movers_secs}
<h2 class="scmonth">최근 실적 발표</h2>
{earnings_block}
{cta_bottom}
{style}"""
    # 링크 카드 문구 (2026-11-23): 가장 임박한 배당·주총 종목으로 짧은 CTA 제목을 만든다.
    _ogt, _ogd = "주식 일정 확인하기", None
    if upcoming:
        _e0 = upcoming[0]; _d0 = _d(_e0["date"])
        if _e0["type"] == "dividend":
            _ogt = f"{_e0['corp_name']} 배당일 바로가기"
            _ogd = (f"주당 {_e0['dps']:,}원 · 기준일 {_d0.month}월 {_d0.day}일" if _e0.get("dps") else f"기준일 {_d0.month}월 {_d0.day}일") + " — 이번 주 배당·실적·주총 일정 확인하기"
        else:
            _ogt = f"{_e0['corp_name']} 주주총회 일정 확인하기"
            _ogd = f"{_d0.month}월 {_d0.day}일 주주총회 — 이번 주 주식 일정 확인하기"
    return head("주식 일정 캘린더 — 배당 기준일·실적 발표·주주총회 | 공모주 나침반",
                "배당 기준일, 주주총회 일정을 날짜순으로 확인하세요. 배당 종목은 주당 배당금까지, 실적 발표는 최근 14일 목록으로 정리합니다. DART 공시 기준.",
                SITE_URL + "/stock-calendar.html", img=img, og_title=_ogt, og_desc=_ogd) + body + FOOT

def home_stock_section(events, today):
    """홈 '이번 주 주식 일정' — 오늘부터 7일 안의 배당·주총 최대 7건."""
    hi = (today + datetime.timedelta(days=7)).isoformat()
    ups = sorted((e for e in events if e["type"] in ("dividend", "meeting") and today.isoformat() <= e["date"] <= hi),
                 key=lambda e: (e["date"], e["corp_name"]))
    if not ups: return ""
    rows = []
    for e in ups[:7]:
        d = datetime.date.fromisoformat(e["date"])
        extra = f" · 주당 {e['dps']:,}원" if e["type"] == "dividend" and e.get("dps") else ""
        rows.append(f"<li style='margin:5px 0;font-size:15px'>{d.month}월 {d.day}일 ({WD[d.weekday()]}) · {STOCK_NAMES[e['type']]} · <b>{esc(e['corp_name'])}</b>{extra} <span style='color:#123a6d;font-weight:700'>{dday(e['date'], today)}</span></li>")
    return ("<section style='background:#fff;border:1px solid #dde4ee;border-radius:12px;padding:16px 18px;margin:0 0 20px'>"
            "<h2 style='font-size:18px;margin:0 0 8px'>🗓️ 이번 주 주식 일정</h2>"
            f"<ul style='list-style:none;margin:0;padding:0'>{''.join(rows)}</ul>"
            "<p style='margin:10px 0 0'><a href='/stock-calendar.html' style='color:#123a6d;font-weight:700'>주식 일정 캘린더 전체 보기 →</a></p></section>")

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
                SITE_URL + "/calculator.html", og_title="공모주 증거금 계산하기") + body + FOOT

# ---------- 글 페이지 확장 (2026-11-23: 결정 글·주식 꿀팁·오늘의 이슈) ----------
# 배경: 쓰레드 조회가 사이트로 이어지지 않는 병목은 링크 부족이 아니라 랜딩할 "글"의 부재였다.
# 결정 글 = 돈이 걸린 순간(청약 마감·상장일)에 맞춘 종목별 글, 꿀팁 = 상시 검색·순환 소재,
# 이슈 = 공모주 밖 시장의 관심을 가져오는 일일 페이지. 셋 다 빌드 때 자동 생성한다.
FEE_EX = 2000  # 청약 수수료 예시 금액 (증권사마다 다름을 본문에 고지)

def _d(iso):
    try: return datetime.date.fromisoformat(iso) if iso else None
    except Exception: return None

def decision_kind(x, today):
    """결정 글 대상 판정. 날짜 파싱 오류가 의심되면 만들지 않는다 (없는 글보다 틀린 글이 나쁘다).
    반환: 'deadline' / 'listing' / 'deadline+listing' / None"""
    ss, se, ld = _d(x.get("sub_start")), _d(x.get("sub_end")), _d(x.get("listing_date"))
    if ss and ld and (ld - ss).days > 120: return None
    if ss and se and se < ss: return None
    kinds = []
    if se and (today - datetime.timedelta(days=2)) <= se <= (today + datetime.timedelta(days=14)) \
            and (x.get("price_final") or x.get("price_high")):
        kinds.append("deadline")
    if ld and (today - datetime.timedelta(days=3)) <= ld <= (today + datetime.timedelta(days=14)) \
            and x.get("price_final"):
        kinds.append("listing")
    return "+".join(kinds) if kinds else None

def decision_banner(x, today):
    if not decision_kind(x, today): return ""
    return (f'<a href="/g/{x["corp_code"]}.html" style="display:block;text-align:center;background:#fdf6e0;color:#7a5b00;'
            f'font-size:17px;font-weight:800;padding:16px 14px;border-radius:14px;text-decoration:none;border:2px solid #e3c766;margin:0 0 14px">'
            f'📖 {esc(x["corp_name"])} 결정 글 — 마감·시나리오 숫자 정리 보기</a>')

def decision_page(x, today, kind, tips, img=""):
    name = esc(x["corp_name"])
    price = x.get("price_final") or x.get("price_high")
    blocks, title_bits, hook = [], [], ""
    if "deadline" in kind:
        se = _d(x["sub_end"]); ss = _d(x.get("sub_start"))
        min_margin = price * 10 // 2
        rows = []
        if ss: rows.append(f"<tr><th>청약 기간</th><td>{ss.isoformat()} ~ {se.isoformat()} ({dday(se.isoformat(), today)} 마감)</td></tr>")
        rows.append(f"<tr><th>공모가</th><td>{esc(price_line(x))}</td></tr>")
        if x.get("underwriter"): rows.append(f"<tr><th>대표주관회사</th><td>{esc(x['underwriter'])}</td></tr>")
        if x.get("demand_ratio"): rows.append(f"<tr><th>수요예측 경쟁률</th><td>{x['demand_ratio']:,} : 1</td></tr>")
        if x.get("listing_date"): rows.append(f"<tr><th>상장 예정일</th><td>{esc(x['listing_date'])}</td></tr>")
        prop = ""
        if x.get("demand_ratio"):
            pr = []
            for amt in (1000000, 3000000, 5000000, 10000000):
                qty = amt // price
                est = qty / x["demand_ratio"]
                est_s = f"약 {est:.2f}주" if est < 10 else f"약 {est:,.0f}주"
                pr.append(f"<tr><th>{amt // 10000:,}만원</th><td>{qty:,}주 청약 → {est_s} 기대</td></tr>")
            prop = (f"<h2 style='font-size:18px;margin:22px 0 8px'>비례로 넣으면 몇 주나 기대할 수 있을까</h2>"
                    f"<table class='facts'>{''.join(pr)}</table>"
                    f"<p class='snote'>수요예측 경쟁률 기준의 단순 계산입니다. 실제 청약 경쟁률과 배정은 달라지며, 균등 배정은 청약 건수로 나뉘어 따로 계산됩니다.</p>")
        blocks.append(f"""<p class="lead">{name} 청약이 <b>{se.month}월 {se.day}일</b>에 마감돼요. 균등만 노린다면 최소 청약 10주 기준 증거금 <b>{min_margin:,}원</b>이면 됩니다.</p>
<table class="facts">{''.join(rows)}</table>
{prop}
<p class="snote">최소 청약 수량과 증거금률은 종목·증권사 공고마다 다를 수 있으니, 청약 전에 주관사 공고에서 한 번 더 확인하세요.</p>""")
        title_bits.append(f"청약 {se.month}월 {se.day}일 마감")
        hook = f"균등 증거금 {min_margin:,}원"
    if "listing" in kind:
        ld = _d(x["listing_date"]); pf = x["price_final"]
        srows = []
        for label, mult in (("시초가 공모가의 90%", 0.9), ("시초가 공모가의 130%", 1.3), ("시초가 공모가의 160%", 1.6), ("시초가 공모가의 200%", 2.0), ("따상 (시초가 200% + 상한가)", 2.6)):
            open_p = round(pf * mult)
            gain = open_p - pf - FEE_EX
            gain_s = f"+{gain:,}원" if gain >= 0 else f"{gain:,}원"
            srows.append(f"<tr><th>{label}</th><td>시초가 {open_p:,}원 · 균등 1주 차익 {gain_s}</td></tr>")
        blocks.append(f"""<p class="lead">{name}가 <b>{ld.month}월 {ld.day}일</b> 상장해요. 공모가 {pf:,}원 기준으로, 시초가가 어디서 열리느냐에 따라 균등 1주의 결과가 이렇게 갈립니다.</p>
{score_box(x)}
<h2 style="font-size:18px;margin:22px 0 8px">시초가 시나리오 — 균등 1주 들고 있으면</h2>
<table class="facts">{''.join(srows)}</table>
<p class="snote">차익은 시초가 − 공모가 − 청약 수수료 예시 {FEE_EX:,}원 기준의 단순 계산입니다. 매도 수수료와 세금은 별도이고, 실제 시초가와 종가는 장에서 정해집니다. 어느 쪽이 될지 단정하는 글이 아니라 숫자를 미리 그려보는 정리예요.</p>""")
        title_bits.append(f"{ld.month}월 {ld.day}일 상장")
        if not hook: hook = f"공모가 {pf:,}원, 시초가 시나리오"
    tip_link = ""
    if tips:
        t = tips[sum(ord(c) for c in x["corp_code"]) % len(tips)]
        tip_link = (f"<p style='margin:20px 0 0'><a href='/tip/{esc(t['slug'])}.html' style='color:#123a6d;font-weight:700'>"
                    f"💡 같이 읽으면 좋은 주식 꿀팁 — {esc(t['title'])} →</a></p>")
    body = f"""<h1>{name} — {' · '.join(title_bits)}</h1>
{ad("detail-top")}
{''.join(blocks)}
{action_btns(x)}
<p style='margin:14px 0 0'><a href="/i/{x['corp_code']}.html" style='color:#123a6d;font-weight:700'>{name} 공모주 상세 정보 보기 →</a></p>
{tip_link}
<p class="src">출처: <a href="{esc(x['dart_url'])}" rel="nofollow">DART 공시 원문</a> ({esc(x['rcept_dt'])} 접수) · 이 글은 정보 정리이며 투자 권유가 아닙니다.</p>
{ad("detail-bottom")}"""
    _ogt = f"{name} 청약 마감 확인하기" if "deadline" in kind else f"{name} 상장일 확인하기"
    _ogd = " · ".join(title_bits + ([hook] if hook else []))
    return head(f"{name} {' · '.join(title_bits)} — {hook} | 공모주 나침반",
                f"{name} 공모주 결정 글. {' · '.join(title_bits)}. {hook}. DART 공시 기준으로 정리했습니다.",
                f"{SITE_URL}/g/{x['corp_code']}.html", img=img, og_title=_ogt, og_desc=_ogd or None) + body + FOOT

def decision_section(items, today):
    """홈 '지금 결정할 것들' — 결정 글이 있는 종목 최대 5개, 임박 순."""
    cands = []
    for x in items:
        k = decision_kind(x, today)
        if not k: continue
        key = x.get("sub_end") if "deadline" in k else x.get("listing_date")
        cands.append((key or "9999", x, k))
    if not cands: return ""
    cands.sort(key=lambda z: z[0])
    rows = []
    for _key, x, k in cands[:5]:
        if "deadline" in k:
            se = _d(x["sub_end"]); price = x.get("price_final") or x.get("price_high")
            rows.append(f"<li style='margin:6px 0;font-size:15px'>🔥 <a href='/g/{x['corp_code']}.html' style='color:#1c2333;font-weight:700;text-decoration:none'>{esc(x['corp_name'])} 청약 {se.month}월 {se.day}일 마감</a> <span style='color:#c62828;font-weight:800'>{dday(x['sub_end'], today)}</span> · 균등 증거금 {price * 10 // 2:,}원</li>")
        else:
            ld = _d(x["listing_date"])
            rows.append(f"<li style='margin:6px 0;font-size:15px'>🚀 <a href='/g/{x['corp_code']}.html' style='color:#1c2333;font-weight:700;text-decoration:none'>{esc(x['corp_name'])} {ld.month}월 {ld.day}일 상장</a> <span style='color:#123a6d;font-weight:800'>{dday(x['listing_date'], today)}</span> · 시초가 시나리오 정리</li>")
    return ("<section style='background:#fff7e8;border:1px solid #ecd9a0;border-radius:12px;padding:16px 18px;margin:0 0 20px'>"
            "<h2 style='font-size:18px;margin:0 0 8px'>🔥 지금 결정할 것들</h2>"
            f"<ul style='list-style:none;margin:0;padding:0'>{''.join(rows)}</ul></section>")

TIP_CATS = {"term": "용어 설명", "chart": "차트 설명", "master": "대가들의 투자법"}

def tip_page(t, tips, img=""):
    rel = [z for z in tips if z["slug"] != t["slug"] and z.get("cat") == t.get("cat")][:3]
    if len(rel) < 3:
        rel += [z for z in tips if z["slug"] != t["slug"] and z not in rel][:3 - len(rel)]
    rel_html = "".join(f"<li style='margin:5px 0;font-size:15px'><a href='/tip/{esc(z['slug'])}.html' style='color:#123a6d;font-weight:700;text-decoration:none'>{esc(z['title'])}</a></li>" for z in rel)
    body = f"""<h1>{esc(t['title'])}</h1>
<p class="lead">{esc(t.get('hook') or '')}</p>
{ad("detail-top")}
<div class="article">{t.get('body') or ''}</div>
{ad("detail-bottom")}
<h2 style="font-size:17px;margin-top:24px">다른 주식 꿀팁</h2>
<ul style="list-style:none;margin:0;padding:0">{rel_html}</ul>
<p style='margin:14px 0 0'><a href="/tip.html" style='color:#123a6d;font-weight:700'>주식 꿀팁 전체 목록 →</a></p>
<p class="snote">교육 목적의 일반 정보입니다. 특정 종목의 매수·매도 권유가 아니며, 투자 판단의 책임은 본인에게 있습니다.</p>"""
    return head(f"{t['title']} | 주식 꿀팁 — 공모주 나침반",
                esc(t.get('hook') or t['title']),
                f"{SITE_URL}/tip/{t['slug']}.html", img=img, og_title=t['title']) + body + FOOT

def tip_index_page(tips, img=""):
    secs = []
    for cat, label in TIP_CATS.items():
        rows = "".join(f"<li style='margin:7px 0;font-size:15.5px'><a href='/tip/{esc(t['slug'])}.html' style='color:#1c2333;font-weight:700;text-decoration:none'>{esc(t['title'])}</a><br><span style='color:#667;font-size:13.5px'>{esc(t.get('hook') or '')}</span></li>"
                       for t in tips if t.get("cat") == cat)
        if rows: secs.append(f"<h2 style='font-size:18px;margin:24px 0 8px'>{label}</h2><ul style='list-style:none;margin:0;padding:0'>{rows}</ul>")
    body = f"""<h1>💡 주식 꿀팁</h1>
<p class="lead">대가들은 어떻게 투자했는지, 차트와 용어는 어떻게 읽는지 — 짧게 정리한 주식 공부 글입니다.</p>
{ad("detail-top")}
{''.join(secs)}
{ad("detail-bottom")}"""
    return head("주식 꿀팁 — 대가들의 투자법·용어·차트 설명 | 공모주 나침반",
                "워런 버핏·피터 린치 같은 대가들의 투자법, PER·RSI 같은 용어, 캔들·거래량 같은 차트 읽는 법을 짧게 정리합니다.",
                SITE_URL + "/tip.html", img=img, og_title="주식 꿀팁 확인하기") + body + FOOT

def tip_section(tips, today):
    if not tips: return ""
    start = today.toordinal() % len(tips)
    pick = [tips[(start + i) % len(tips)] for i in range(min(4, len(tips)))]
    rows = "".join(f"<li style='margin:5px 0;font-size:15px'>💡 <a href='/tip/{esc(t['slug'])}.html' style='color:#1c2333;font-weight:700;text-decoration:none'>{esc(t['title'])}</a></li>" for t in pick)
    return ("<section style='background:#fff;border:1px solid #dde4ee;border-radius:12px;padding:16px 18px;margin:20px 0'>"
            "<h2 style='font-size:18px;margin:0 0 8px'>💡 오늘의 주식 꿀팁</h2>"
            f"<ul style='list-style:none;margin:0;padding:0'>{rows}</ul>"
            "<p style='margin:10px 0 0'><a href='/tip.html' style='color:#123a6d;font-weight:700'>주식 꿀팁 전체 보기 →</a></p></section>")

def issue_page(market, today, tips, img=""):
    def val_fmt(v):
        eok = v / 100.0
        return f"{eok / 10000:.1f}조원" if eok >= 10000 else f"{eok:,.0f}억원"
    tipmap = {t["slug"]: t for t in tips}
    def tip_link(slug, text):
        t = tipmap.get(slug)
        return f"<p style='margin:6px 0 0;font-size:14px'><a href='/tip/{slug}.html' style='color:#123a6d;font-weight:700'>💡 {esc(text)} →</a></p>" if t else ""
    blocks = []
    mdate_s = (market or {}).get("date") or today.isoformat()
    md = _d(mdate_s) or today
    day_label = "오늘" if mdate_s == today.isoformat() else f"{md.month}월 {md.day}일"
    def stock_rows(items, up):
        out = []
        for it in items:
            color = "#c62828" if up else "#1565c0"
            sign = "+" if up else ""
            out.append(f"<div class='scrow'><a class='scname' style='text-decoration:none' href='https://finance.naver.com/item/main.naver?code={esc(it['code'])}' target='_blank' rel='nofollow noopener'>{esc(it['name'])}</a>"
                       f"<span class='scmk'>{esc(it['market'])}</span>"
                       f"<span class='scmv'>{it['close']:,}원 <b style='color:{color}'>{sign}{it['ratio']:.2f}%</b> · 거래대금 {val_fmt(it['value'])}</span></div>")
        return "".join(out) or "<p style='color:#889;font-size:14.5px'>해당 종목이 없어요.</p>"
    if market and market.get("upper"):
        blocks.append(f"<h2 style='font-size:19px;margin:22px 0 6px;color:#c62828'>🔺 {day_label} 상한가 {len(market['upper'])}종목</h2>"
                      f"<p style='font-size:14.5px;color:#345;margin:0 0 6px'>가격제한폭까지 오른 종목들입니다. 상한가 다음 날은 시초가부터 크게 흔들리는 경우가 많아요 — 왜 올랐는지보다, 거래량이 실렸는지를 먼저 보는 게 순서입니다.</p>"
                      f"{stock_rows(market['upper'], True)}"
                      + tip_link("volume", "거래량 읽는 법 — 가격보다 먼저 움직이는 신호"))
    if market and market.get("lower"):
        blocks.append(f"<h2 style='font-size:19px;margin:22px 0 6px;color:#1565c0'>🔻 {day_label} 하한가 {len(market['lower'])}종목</h2>"
                      f"<p style='font-size:14.5px;color:#345;margin:0 0 6px'>가격제한폭까지 떨어진 종목들입니다. 하한가에 물리면 팔고 싶어도 못 파는 날이 생깁니다 — 대가들이 손절 원칙을 먼저 세워두는 이유예요.</p>"
                      f"{stock_rows(market['lower'], False)}"
                      + tip_link("livermore", "제시 리버모어 — 추세를 따르고 손절을 먼저 정한 사람"))
    if not blocks:
        blocks.append("<p>아직 수집된 상한가·하한가 데이터가 없어요. 장이 열린 날 마감 뒤에 업데이트됩니다.</p>")
    body = f"""<h1>📌 오늘의 이슈 종목</h1>
<p class="lead">{md.month}월 {md.day}일 시장에서 가장 크게 움직인 종목들입니다. 공모주 밖에서도 시장 전체의 온도를 읽는 자리예요.</p>
{ad("detail-top")}
{''.join(blocks)}
{ad("detail-bottom")}
<div style="display:flex;gap:10px;flex-wrap:wrap;margin:20px 0 6px">
<a href="/stock-calendar.html" style="flex:1 1 240px;display:block;text-align:center;background:#123a6d;color:#fff;font-size:17px;font-weight:800;padding:16px 14px;border-radius:14px;text-decoration:none">🗓️ 배당·주총 주식 캘린더 보기</a>
<a href="/tip.html" style="flex:1 1 240px;display:block;text-align:center;background:#eef3fa;color:#123a6d;font-size:17px;font-weight:800;padding:16px 14px;border-radius:14px;text-decoration:none;border:2px solid #123a6d">💡 주식 꿀팁 더 보기</a></div>
<p style='color:#889;font-size:12.5px'>{(market or {}).get('collected_at', '')} 기준 · 네이버 증권 시세로 가격제한폭 도달 종목을 계산했습니다. 장중에는 바뀔 수 있어요.</p>"""
    # 링크 카드 문구 (2026-11-23): 그날 상한가·하한가 데이터로 짧은 CTA 제목을 만든다.
    _ogt, _ogd = "오늘의 이슈 종목 확인하기", None
    if market and market.get("upper"):
        _ogt = "30% 상한가 종목 확인하기"
        _top = max(market["upper"], key=lambda it: it.get("value", 0))
        _ogd = f"{_top['name']} {_top['close']:,}원 +{_top['ratio']:.2f}% · 상한가 {len(market['upper'])}종목 전체 보기"
    elif market and market.get("lower"):
        _ogt = "하한가 종목 확인하기"
        _top = max(market["lower"], key=lambda it: it.get("value", 0))
        _ogd = f"{_top['name']} {_top['close']:,}원 {_top['ratio']:.2f}% · 하한가 {len(market['lower'])}종목 전체 보기"
    return head(f"오늘의 이슈 종목 — {md.month}월 {md.day}일 상한가·하한가 | 공모주 나침반",
                f"{md.month}월 {md.day}일 상한가·하한가 종목과 거래대금을 정리합니다. 시장 전체의 온도를 읽는 페이지입니다.",
                SITE_URL + "/issue.html", img=img, og_title=_ogt, og_desc=_ogd) + body + FOOT

def main():
    data = json.load(open(os.path.join(ROOT, "data", "ipos.json"), encoding="utf-8"))
    items = data["items"]
    try:
        cal = json.load(open(os.path.join(ROOT, "data", "calendar.json"), encoding="utf-8"))
        events = cal.get("events", [])
    except Exception:
        events = []
    try:
        market = json.load(open(os.path.join(ROOT, "data", "market.json"), encoding="utf-8"))
    except Exception:
        market = None
    try:
        tips = json.load(open(os.path.join(ROOT, "data", "tips.json"), encoding="utf-8")).get("items", [])
    except Exception:
        tips = []
    today = datetime.date.today()
    dist = os.path.join(ROOT, "dist")
    shutil.rmtree(dist, ignore_errors=True)
    os.makedirs(os.path.join(dist, "i"))
    os.makedirs(os.path.join(dist, "cards"))
    os.makedirs(os.path.join(dist, "g"))
    os.makedirs(os.path.join(dist, "tip"))
    default_img = f"{SITE_URL}/cards/default.png" if _card_img(os.path.join(dist, "cards", "default.png"), "공모주 나침반", "청약 일정 한눈에", "공모가·수요예측 점수까지 정리") else ""
    cards = "\n".join(card(x, today) for x in items)
    home_banner = ('<div style="display:flex;gap:10px;flex-wrap:wrap;margin:16px 0 20px">'
                   '<a href="/calendar.html" style="flex:1 1 240px;display:block;text-align:center;background:#123a6d;color:#fff;font-size:19px;font-weight:800;padding:18px 14px;border-radius:14px;text-decoration:none">📅 공모주 일정 캘린더</a>'
                   '<a href="/calculator.html" style="flex:1 1 240px;display:block;text-align:center;background:#eef3fa;color:#123a6d;font-size:19px;font-weight:800;padding:18px 14px;border-radius:14px;text-decoration:none;border:2px solid #123a6d">🧮 공모주 증거금 계산기</a></div>')
    home = head("공모주 나침반 | 공모주 청약 일정·공모가·수요예측",
                "다가오는 공모주 청약 일정과 공모가, 수요예측 결과를 DART 공시 기준으로 정리합니다.",
                SITE_URL + "/", img=default_img, og_title="공모주 청약 일정 확인하기") + home_banner + decision_section(items, today) + home_stock_section(events, today) + f"<h1>공모주 청약 일정</h1><p class='upd'>업데이트 {esc(data['updated'][:16].replace('T', ' '))} · {len(items)}개 종목</p><div class='grid'>{cards}</div>" + tip_section(tips, today) + FOOT
    open(os.path.join(dist, "index.html"), "w", encoding="utf-8").write(home)
    open(os.path.join(dist, "calendar.html"), "w", encoding="utf-8").write(calendar_page(items, today))
    # 캘린더 카드 이미지도 가장 임박한 일정으로 동적 생성 (2026-11-23) — 파일명에 날짜를 넣어 메타 이미지 캐시를 우회한다.
    _cal_t, _cal_l1, _cal_l2 = "주식 일정 캘린더", "배당·실적·주총 한눈에", "DART 공시 기준 일정 정리"
    _up = sorted((e for e in events if e["type"] in ("dividend", "meeting") and e["date"] >= today.isoformat()), key=lambda e: (e["date"], e["corp_name"]))
    if _up:
        _e0 = _up[0]; _d0 = _d(_e0["date"])
        if _e0["type"] == "dividend":
            _cal_t = f"{_e0['corp_name']} 배당 기준일"
            _cal_l1 = f"{_d0.month}월 {_d0.day}일" + (f" · 주당 {_e0['dps']:,}원" if _e0.get("dps") else "")
            _cal_l2 = "이번 주 배당·실적·주총 일정"
        else:
            _cal_t = f"{_e0['corp_name']} 주주총회"
            _cal_l1 = f"{_d0.month}월 {_d0.day}일 개최"
            _cal_l2 = "이번 주 배당·실적·주총 일정"
    _simg_name = f"stockcal-{today.strftime('%m%d')}.png"
    simg = f"{SITE_URL}/cards/{_simg_name}" if _card_img(os.path.join(dist, "cards", _simg_name), _cal_t, _cal_l1, _cal_l2) else ""
    open(os.path.join(dist, "stock-calendar.html"), "w", encoding="utf-8").write(stock_calendar_page(events, today, simg, market))
    open(os.path.join(dist, "calculator.html"), "w", encoding="utf-8").write(calculator_page(items, today))
    _iimg = default_img
    if market and (market.get("upper") or market.get("lower")):
        _iname = f"issue-{today.strftime('%m%d')}.png"
        if market.get("upper"):
            _top = max(market["upper"], key=lambda it: it.get("value", 0))
            _il1, _il2 = f"상한가 {len(market['upper'])}종목", f"{_top['name']} +{_top['ratio']:.2f}%"
        else:
            _top = max(market["lower"], key=lambda it: it.get("value", 0))
            _il1, _il2 = f"하한가 {len(market['lower'])}종목", f"{_top['name']} {_top['ratio']:.2f}%"
        if _card_img(os.path.join(dist, "cards", _iname), "오늘의 이슈 종목", _il1, _il2):
            _iimg = f"{SITE_URL}/cards/{_iname}"
    open(os.path.join(dist, "issue.html"), "w", encoding="utf-8").write(issue_page(market, today, tips, _iimg))
    open(os.path.join(dist, "tip.html"), "w", encoding="utf-8").write(tip_index_page(tips, default_img))
    for t in tips:
        open(os.path.join(dist, "tip", t["slug"] + ".html"), "w", encoding="utf-8").write(tip_page(t, tips, default_img))
    g_made = []
    for x in items:
        kind = decision_kind(x, today)
        if not kind: continue
        gimg = f"{SITE_URL}/cards/g{x['corp_code']}.png" if _card_img(os.path.join(dist, "cards", "g" + x["corp_code"] + ".png"), x["corp_name"], "지금 결정할 숫자", " · ".join(b for b in [f"청약 {mdd(x['sub_end'])} 마감" if "deadline" in kind else "", f"상장 {mdd(x['listing_date'])}" if "listing" in kind else ""] if b)) else ""
        open(os.path.join(dist, "g", x["corp_code"] + ".html"), "w", encoding="utf-8").write(decision_page(x, today, kind, tips, gimg))
        g_made.append(x["corp_code"])
    for x in items:
        cimg = f"{SITE_URL}/cards/{x['corp_code']}.png" if og_card(os.path.join(dist, "cards", x["corp_code"] + ".png"), x, today) else ""
        open(os.path.join(dist, "i", x["corp_code"] + ".html"), "w", encoding="utf-8").write(detail(x, today, cimg))
        if x.get("sub_start"):
            open(os.path.join(dist, "i", x["corp_code"] + ".ics"), "w", encoding="utf-8", newline="").write(ics_file(x))
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in ("/", "/calendar.html", "/calculator.html", "/stock-calendar.html", "/issue.html", "/tip.html"):
        sm.append(f"<url><loc>{SITE_URL}{u}</loc><lastmod>{data['updated'][:10]}</lastmod></url>")
    for x in items:
        sm.append(f"<url><loc>{SITE_URL}/i/{x['corp_code']}.html</loc><lastmod>{data['updated'][:10]}</lastmod></url>")
    for code in g_made:
        sm.append(f"<url><loc>{SITE_URL}/g/{code}.html</loc><lastmod>{data['updated'][:10]}</lastmod></url>")
    for t in tips:
        sm.append(f"<url><loc>{SITE_URL}/tip/{t['slug']}.html</loc><lastmod>{data['updated'][:10]}</lastmod></url>")
    sm.append("</urlset>")
    open(os.path.join(dist, "sitemap.xml"), "w", encoding="utf-8").write("\n".join(sm))
    open(os.path.join(dist, "robots.txt"), "w", encoding="utf-8").write(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")
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
