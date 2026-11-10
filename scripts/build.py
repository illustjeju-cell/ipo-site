# -*- coding: utf-8 -*-
"""공모주 나침반 빌드 — data/ipos.json 을 정적 사이트로 만든다."""
import json, os, re, html, shutil, datetime

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

def head(title, desc, url, body_cls=""):
    ads = f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE}" crossorigin="anonymous"></script>' if ADSENSE else ""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website"><meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{url}">
{ads}<style>{CSS}</style></head>
<body class="{body_cls}"><header class="site"><a href="/">공모주 나침반</a><nav><a href="/calendar.html">📅 일정 캘린더</a></nav></header><main>"""

FOOT = """</main><footer>공모 일정과 공모가는 금융감독원 전자공시시스템(DART) 공시를 바탕으로 정리합니다. 투자 판단의 책임은 본인에게 있습니다.</footer></body></html>"""

def price_line(x):
    if x.get("price_final"): return f"확정공모가 {won(x['price_final'])}"
    if x.get("price_low") and x.get("price_high"): return f"희망공모가 {won(x['price_low'])} ~ {won(x['price_high'])}"
    return "공모가 미정"

def card(x, today):
    sub = ""
    if x.get("sub_start"):
        sub = f"청약 {x['sub_start']} ~ {x.get('sub_end') or x['sub_start']} <b>{dday(x['sub_start'], today)}</b>"
    return f"""<a class="card" href="/i/{x['corp_code']}.html">
<div class="cname">{esc(x['corp_name'])} <span class="stage">{esc(x['stage'])}</span></div>
<div class="cprice">{esc(price_line(x))}</div>
<div class="cmeta">{sub}</div>
<div class="cmeta">{esc(x.get('underwriter') or '')}</div></a>"""

def detail(x, today):
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
<table class="facts">{"".join(rows)}</table>
<p class="src">출처: <a href="{esc(x['dart_url'])}" rel="nofollow">DART 공시 원문</a> ({esc(x['rcept_dt'])} 접수)</p>"""
    return head(f"{x['corp_name']} 공모주 청약 일정·공모가 | 공모주 나침반",
                f"{x['corp_name']} 공모주 청약 일정, 희망공모가·확정공모가, 수요예측 결과를 정리했습니다.",
                f"{SITE_URL}/i/{x['corp_code']}.html") + body + FOOT

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

def main():
    data = json.load(open(os.path.join(ROOT, "data", "ipos.json"), encoding="utf-8"))
    items = data["items"]
    today = datetime.date.today()
    dist = os.path.join(ROOT, "dist")
    shutil.rmtree(dist, ignore_errors=True)
    os.makedirs(os.path.join(dist, "i"))
    cards = "\n".join(card(x, today) for x in items)
    home = head("공모주 나침반 | 공모주 청약 일정·공모가·수요예측",
                "다가오는 공모주 청약 일정과 공모가, 수요예측 결과를 DART 공시 기준으로 정리합니다.",
                SITE_URL + "/") + f"<h1>공모주 청약 일정</h1><p class='upd'>업데이트 {esc(data['updated'][:16].replace('T', ' '))} · {len(items)}개 종목</p><div class='grid'>{cards}</div>" + FOOT
    open(os.path.join(dist, "index.html"), "w", encoding="utf-8").write(home)
    open(os.path.join(dist, "calendar.html"), "w", encoding="utf-8").write(calendar_page(items, today))
    for x in items:
        open(os.path.join(dist, "i", x["corp_code"] + ".html"), "w", encoding="utf-8").write(detail(x, today))
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
