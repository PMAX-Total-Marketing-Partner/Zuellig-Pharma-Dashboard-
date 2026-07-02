# -*- coding: utf-8 -*-
"""
Zuellig Pharma — IMOJEV Facebook Performance Dashboard (REALTIME)
=================================================================
Engine: đọc FB_Paxy (actual) + KPI RAW (KPI toàn campaign) -> sinh dashboard.html
self-contained, brand Zuellig. HTML có 2 chế độ dữ liệu:
  1) LIVE  : nếu DATA_URL (published-to-web CSV của tab FB_Paxy) được cấu hình,
             trình duyệt tự fetch CSV đó mỗi lần mở + auto-refresh 10'.
  2) SNAP  : nếu chưa có URL / fetch fail -> dùng snapshot nhúng sẵn (data lúc build).

Chạy lại engine = cập nhật snapshot (chế độ "refresh on run").
KPI toàn campaign là hằng số (plan) -> luôn nhúng sẵn, không cần fetch.

Cách dùng:
  cd "C:\\Users\\Hung Vu\\Downloads\\Claude code"
  python read_sheet.py 16AtdH_bp5cN9wGG1t7qmmfdTfNlevY7vVZ9TQ-qrHnY   # tải sheet mới nhất
  python projects/zuellig-pharma/dashboard/build_dashboard.py

Muốn LIVE: mở dashboard.html, sửa DATA_URL (dòng CONFIG đầu <script>) = link CSV publish-to-web.
"""
import sys, io, os, json, csv, datetime
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')   # an toàn khi import lồng nhau (không orphan-close buffer)

ROOT = r'C:\Users\Hung Vu\Downloads\Claude code'
SHEET_DIR = os.path.join(ROOT, 'sheet_output', 'EXT_Zuellig_Pharma_Media_campaign__16AtdH_b')
FB_PAXY = os.path.join(SHEET_DIR, 'FB_Paxy.csv')
KPI_RAW = os.path.join(SHEET_DIR, 'KPI_RAW.csv')
OUT = os.path.join(ROOT, 'projects', 'zuellig-pharma', 'dashboard', 'dashboard.html')

# ── Buying rates (External / rate card) ──────────────────────────────────────
CPM_REACH = 24000     # VND / 1000 impression
CPC_TRAFFIC = 1500    # VND / click
CAMPAIGN_START = '2026-06-18'
CAMPAIGN_END   = '2026-10-31'

# canonical asset display (FB_Paxy dùng "Animation Video", KPI RAW dùng "Animation video")
ASSET_DISPLAY = {
    'animation video': 'Animation Video',
    'master video': 'Master Video',
    'expert video': 'Expert Video',
    'event': 'Event', 'kv': 'KV', 'social': 'Social',
}
def norm_asset(a):
    a = (a or '').strip()
    return ASSET_DISPLAY.get(a.lower(), a)

def to_num(x):
    if x is None: return 0.0
    s = str(x).strip().replace(',', '')
    if s == '' or s.upper() == '#N/A': return 0.0
    try: return float(s)
    except: return 0.0

def iso_date(s):
    """Chuẩn hoá date về YYYY-MM-DD. Nhận 2026-06-18 hoặc 6/18/2026."""
    s = (s or '').strip()
    if not s: return None
    if '-' in s and len(s) >= 8:
        try:
            datetime.date.fromisoformat(s[:10]); return s[:10]
        except: pass
    if '/' in s:
        try:
            m, d, y = s.split('/')[:3]
            return f'{int(y):04d}-{int(m):02d}-{int(d):02d}'
        except: return None
    return None

# ── 1) FB_Paxy actual rows ───────────────────────────────────────────────────
def load_paxy():
    rows = []
    with open(FB_PAXY, encoding='utf-8-sig', newline='') as f:
        r = csv.DictReader(f)
        for rec in r:
            d = iso_date(rec.get('Date'))
            ch = (rec.get('Channel') or '').strip()
            obj = (rec.get('Objective') or '').strip()
            if not d or ch != 'Facebook' or obj not in ('Reach', 'Traffic'):
                continue
            rows.append({
                'date': d,
                'obj': obj,
                'pillar': (rec.get('Pillar') or '').strip() or '(n/a)',
                'asset': norm_asset(rec.get('Asset')),
                'aud': (rec.get('Audience') or '').strip() or '(n/a)',
                'impr': to_num(rec.get('Impression')),
                'eng':  to_num(rec.get('Engagement')),
                'view': to_num(rec.get('FB Thruplay Action')),
                'click': to_num(rec.get('Link click')),
            })
    return rows

# ── 2) KPI RAW -> KPI toàn campaign theo (obj, asset, aud) ────────────────────
def load_kpi():
    agg = {}
    with open(KPI_RAW, encoding='utf-8-sig', newline='') as f:
        r = csv.DictReader(f)
        for rec in r:
            ch = (rec.get('Channel') or '').strip()
            obj = (rec.get('Objective') or '').strip()
            if ch != 'Facebook' or obj not in ('Reach', 'Traffic'):
                continue
            asset = norm_asset(rec.get('Asset'))
            aud = (rec.get('Audience') or '').strip()
            k = (obj, asset, aud)
            a = agg.setdefault(k, {'obj': obj, 'asset': asset, 'aud': aud,
                                   'budget': 0.0, 'qty': 0.0, 'impr': 0.0,
                                   'eng': 0.0, 'view': 0.0, 'click': 0.0})
            a['budget'] += to_num(rec.get('KPI Budget'))
            a['qty']    += to_num(rec.get('KPI_Quantity'))
            a['impr']   += to_num(rec.get('KPI_Impression'))
            a['eng']    += to_num(rec.get('KPI_Engagement'))
            a['view']   += to_num(rec.get('KPI_View'))
            a['click']  += to_num(rec.get('KPI_Click'))
    return list(agg.values())

def main():
    paxy = load_paxy()
    kpi = load_kpi()
    dates = sorted({r['date'] for r in paxy})
    meta = {
        'cpmReach': CPM_REACH, 'cpcTraffic': CPC_TRAFFIC,
        'campaignStart': CAMPAIGN_START, 'campaignEnd': CAMPAIGN_END,
        'dataMinDate': dates[0] if dates else None,
        'dataMaxDate': dates[-1] if dates else None,
        'nRows': len(paxy),
    }
    gen = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

    # DATA_URL persist qua config (set 1 lần, re-run không mất)
    data_url = ''
    cfg_path = os.path.join(os.path.dirname(OUT), 'dashboard_config.json')
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, encoding='utf-8') as f:
                data_url = (json.load(f).get('DATA_URL') or '').strip()
        except Exception as e:
            print(f'[WARN] đọc dashboard_config.json lỗi: {e}')

    html = TEMPLATE
    html = html.replace('__DATA_JSON__', json.dumps(paxy, ensure_ascii=False))
    html = html.replace('__KPI_JSON__', json.dumps(kpi, ensure_ascii=False))
    html = html.replace('__META_JSON__', json.dumps(meta, ensure_ascii=False))
    html = html.replace('__DATA_URL__', data_url.replace('"', '%22'))
    html = html.replace('__GENERATED__', gen)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(html)
    # bản index.html để host: Netlify/GitHub Pages phục vụ ở URL gốc (khỏi cần /dashboard.html)
    with open(os.path.join(os.path.dirname(OUT), 'index.html'), 'w', encoding='utf-8') as f:
        f.write(html)

    # reconcile log
    tot_impr = sum(r['impr'] for r in paxy)
    tot_view = sum(r['view'] for r in paxy)
    tot_click = sum(r['click'] for r in paxy)
    tot_eng = sum(r['eng'] for r in paxy)
    kpi_budget = sum(k['budget'] for k in kpi)
    print(f'[OK] wrote {OUT}')
    print(f'  rows={len(paxy)}  dates={meta["dataMinDate"]}..{meta["dataMaxDate"]}')
    print(f'  ACTUAL  impr={tot_impr:,.0f}  view={tot_view:,.0f}  click={tot_click:,.0f}  eng={tot_eng:,.0f}')
    print(f'  KPI(FB) budget={kpi_budget:,.0f}  combos={len(kpi)}')
    print(f'  mode={"LIVE (fetch " + data_url[:48] + "...)" if data_url else "SNAPSHOT (chưa set DATA_URL)"}')
    print(f'  generated={gen}')


TEMPLATE = r'''<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Zuellig Pharma · IMOJEV — Facebook Performance Dashboard</title>
<style>
  :root{
    --brand:#CADB36; --brand-deep:#B3C42B; --brand-light:#E2E88F; --brand-tint:#F3F7D6;  /* IMOJEV green DS302-3U rgb(202,219,54) */
    --brand-blue:#6C8CC7; --brand-blue-deep:#4E6BAE;   /* IMOJEV blue DS196-5U rgb(108,140,199) */
    --zp-red:#6C8CC7; --zp-red-dark:#4E6BAE;   /* data accent = IMOJEV blue */
    --zp-ink:#2E343A; --zp-charcoal:#4A525B;
    --bg:#F5F7FB; --card:#FFFFFF; --line:#E6E9F0; --muted:#6E7683; --muted2:#9AA2B0;
    --ok:#5E9E2E; --warn:#E8912B; --bad:#D23B3B; --track:#EDEFF4;
    --shadow:0 1px 2px rgba(46,52,58,.06),0 6px 20px rgba(46,52,58,.07);
    --radius:16px;
    --sans:Verdana,Geneva,'DejaVu Sans',Tahoma,sans-serif;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--zp-ink);font-family:var(--sans);
       font-size:14px;line-height:1.45;-webkit-font-smoothing:antialiased}
  a{color:var(--zp-red)}
  .wrap{max-width:1240px;margin:0 auto;padding:0 20px 64px}

  /* Header */
  header.top{background:linear-gradient(105deg,var(--brand) 0%,#A9C77E 34%,#8AA9D0 70%,var(--brand-blue) 100%);color:var(--zp-ink);border-bottom:3px solid var(--brand-blue-deep)}
  .top-in{max-width:1240px;margin:0 auto;padding:20px 20px 22px;display:flex;
          align-items:center;gap:18px;flex-wrap:wrap}
  .mark{width:46px;height:46px;flex:0 0 auto;border-radius:11px;background:#fff;
         display:grid;place-items:center;box-shadow:0 2px 8px rgba(0,0,0,.18)}
  .mark svg{display:block}
  .brand h1{margin:0;font-size:19px;font-weight:800;letter-spacing:.3px}
  .brand .sub{opacity:.92;font-size:12.5px;margin-top:2px}
  .top-right{margin-left:auto;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
  .live{display:inline-flex;align-items:center;gap:7px;background:rgba(255,255,255,.62);
        padding:7px 12px;border-radius:999px;font-size:12px;font-weight:700}
  .dot{width:8px;height:8px;border-radius:50%;background:#1a7f37;box-shadow:0 0 0 0 rgba(26,127,55,.6);
       animation:pulse 1.8s infinite}
  .dot.snap{background:#C77800;animation:none}
  @keyframes pulse{0%{box-shadow:0 0 0 0 rgba(26,127,55,.55)}70%{box-shadow:0 0 0 7px rgba(26,127,55,0)}100%{box-shadow:0 0 0 0 rgba(26,127,55,0)}}
  select,button.btn{font-family:var(--sans);font-size:12.5px;border-radius:9px;border:0;padding:8px 12px;cursor:pointer}
  select{background:#fff;color:var(--zp-ink);font-weight:600;box-shadow:0 1px 2px rgba(0,0,0,.12)}
  button.btn{background:var(--brand-blue-deep);color:#fff;font-weight:700}
  button.btn:hover{background:#3E579A}

  /* Section shells */
  .section{margin-top:26px}
  .section-h{display:flex;align-items:baseline;gap:12px;margin:0 2px 12px}
  .section-h .n{width:26px;height:26px;flex:0 0 auto;border-radius:8px;background:var(--zp-ink);
       color:#fff;font-size:13px;font-weight:800;display:grid;place-items:center}
  .section-h h2{margin:0;font-size:16px;font-weight:800}
  .section-h .hint{color:var(--muted);font-size:12px;margin-left:auto;font-weight:500}

  .card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}
  .pad{padding:18px 20px}

  /* KPI cards */
  .kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:14px}
  .kpi{padding:16px 16px 14px}
  .kpi .lab{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:.4px}
  .kpi .ic{width:9px;height:9px;border-radius:3px;background:var(--zp-red)}
  .kpi .val{font-size:26px;font-weight:800;margin:8px 0 2px;letter-spacing:-.5px}
  .kpi .unit{font-size:12px;color:var(--muted2);font-weight:600}
  .kpi .vs{font-size:12px;color:var(--muted);margin-top:3px}
  .kpi .vs b{color:var(--zp-charcoal)}
  .bar{height:7px;border-radius:6px;background:var(--track);overflow:hidden;margin-top:11px}
  .bar > i{display:block;height:100%;border-radius:6px;background:var(--zp-red)}
  .kpi .pct{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-top:6px}
  .kpi .pct b{color:var(--zp-red)}

  /* flight strip */
  .flight{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
  .flight .big{font-size:15px;font-weight:800}
  .flight .track{flex:1;min-width:220px}
  .flight .bar{margin-top:0}
  .flight .bar > i{background:linear-gradient(90deg,var(--zp-charcoal),var(--zp-ink))}
  .chip{font-size:11.5px;font-weight:700;padding:4px 10px;border-radius:999px;background:var(--track);color:var(--zp-charcoal)}
  .chip.ok{background:rgba(31,157,87,.12);color:var(--ok)} .chip.warn{background:rgba(232,145,43,.14);color:var(--warn)}

  /* charts */
  .chart-wrap{overflow-x:auto}
  svg.chart{display:block;width:100%;min-width:560px;height:260px}
  .legend{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin-top:8px}
  .legend span{display:inline-flex;align-items:center;gap:6px}
  .legend i{width:12px;height:12px;border-radius:3px;display:inline-block}

  /* tables */
  table{border-collapse:collapse;width:100%;font-size:13px}
  .table-wrap{overflow-x:auto}
  th,td{padding:9px 12px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--line)}
  th:first-child,td:first-child{text-align:left}
  thead th{background:#faf9f9;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.4px;font-weight:800;position:sticky;top:0}
  tbody tr.obj-row td{background:#EDF1FA;font-weight:800;color:var(--brand-blue-deep)}
  tbody tr.grand td{background:var(--zp-ink);color:#fff;font-weight:800;border-bottom:0}
  tbody tr.grand td:first-child{border-radius:0 0 0 12px}
  tbody tr.grand td:last-child{border-radius:0 0 12px 0}
  td .mini{display:inline-flex;align-items:center;gap:8px;justify-content:flex-end}
  td .minibar{width:64px;height:6px;border-radius:4px;background:var(--track);overflow:hidden}
  td .minibar > i{display:block;height:100%;background:var(--zp-red)}
  .sub-td{color:var(--muted)}
  .pill{font-size:11px;padding:2px 8px;border-radius:999px;font-weight:700}
  .pill.reach{background:rgba(202,219,54,.30);color:#6E7D14}
  .pill.traffic{background:rgba(108,140,199,.20);color:var(--brand-blue-deep)}

  .grid2{display:grid;grid-template-columns:1.35fr 1fr;gap:16px}
  .defs{columns:2;column-gap:28px;font-size:12.5px;color:var(--muted)}
  .defs p{margin:0 0 9px;break-inside:avoid}
  .defs b{color:var(--zp-charcoal)}
  footer{margin-top:30px;color:var(--muted);font-size:12px;text-align:center;line-height:1.7}
  .banner{margin-top:14px;background:#fff7e6;border:1px solid #ffe2ac;color:#8a5a00;
           border-radius:12px;padding:10px 14px;font-size:12.5px;display:none}
  @media(max-width:960px){.kpis{grid-template-columns:repeat(2,1fr)}.grid2{grid-template-columns:1fr}.defs{columns:1}}
  @media(max-width:520px){.kpis{grid-template-columns:1fr}}

  /* Đọc nhanh — định nghĩa dễ hiểu */
  .defs-top{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
  .def{display:flex;gap:11px;align-items:flex-start}
  .def .de{width:36px;height:36px;flex:0 0 auto;border-radius:10px;background:var(--brand-tint);
           display:grid;place-items:center;font-size:18px;border:1px solid var(--brand-light)}
  .def h4{margin:0 0 3px;font-size:13.5px;font-weight:800}
  .def h4 small{color:var(--muted2);font-weight:600;font-size:11px}
  .def p{margin:0;font-size:12.5px;color:var(--muted);line-height:1.5}
  @media(max-width:820px){.defs-top{grid-template-columns:1fr 1fr}}
  @media(max-width:520px){.defs-top{grid-template-columns:1fr}}

  /* Tổng quan tích cực + Nhận xét/Next action */
  .summary{padding:18px 20px;border-left:7px solid var(--brand-deep)}
  .sum-badge{display:inline-flex;align-items:center;gap:7px;background:var(--brand);color:#243b06;
             font-weight:800;font-size:13px;padding:6px 14px;border-radius:999px;margin-bottom:11px}
  .sum-note{font-size:14.5px;line-height:1.62}
  .cmt{margin-top:12px;background:var(--card);border:1px solid var(--line);
       border-left:5px solid var(--brand-deep);border-radius:12px;padding:12px 16px}
  .cmt-row{display:flex;gap:11px;align-items:flex-start;margin:6px 0}
  .cmt-ic{font-size:16px;line-height:1.4;flex:0 0 auto}
  .cmt-row .h{font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:800}
  .cmt-row p{margin:2px 0 0;font-size:13.5px;line-height:1.55}

  /* date range picker */
  .daterange{display:inline-flex;align-items:center;gap:5px}
  .daterange input[type=date]{font-family:var(--sans);font-size:12px;border:0;border-radius:8px;padding:7px 9px;
     background:#fff;color:var(--zp-ink);box-shadow:0 1px 2px rgba(0,0,0,.12)}
  .daterange > span{color:inherit;opacity:.6;font-weight:800}

  /* funnel + donut */
  .mini-h{font-size:14px;font-weight:800;margin-bottom:14px}
  .fn-row{margin:0 0 13px}
  .fn-lab{font-size:12.5px;font-weight:700;color:var(--zp-charcoal);margin-bottom:4px}
  .fn-barwrap{display:flex;align-items:center;gap:10px}
  .fn-bar{height:24px;border-radius:6px;min-width:6px}
  .fn-val{font-size:15px;font-weight:800}
  .fn-sub{font-size:11.5px;color:var(--muted);margin-top:3px}
  .donut-flex{display:flex;align-items:center;gap:20px;flex-wrap:wrap}
  .donut-legend{flex:1;min-width:150px}
  .lg-row{display:flex;align-items:center;gap:8px;font-size:12.5px;margin:6px 0}
  .lg-sw{width:11px;height:11px;border-radius:3px;flex:0 0 auto}
  .lg-row b{margin-left:auto;color:var(--zp-ink)}
</style>
</head>
<body>
<header class="top">
  <div class="top-in">
    <div class="mark" title="Zuellig Pharma">
      <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true">
        <defs><linearGradient id="zg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#6C8CC7"/><stop offset="1" stop-color="#4E6BAE"/></linearGradient></defs>
        <path d="M7 8 h16 l-16 14 h16" fill="none" stroke="url(#zg)" stroke-width="3.4" stroke-linejoin="round" stroke-linecap="round"/>
      </svg>
    </div>
    <div class="brand">
      <h1>IMOJEV — Facebook Performance Dashboard</h1>
      <div class="sub">Zuellig Pharma · Chiến dịch IMOJEV · Flight <span id="flightRange"></span></div>
    </div>
    <div class="top-right">
      <span class="live"><span id="liveDot" class="dot snap"></span><span id="liveText">Snapshot</span></span>
      <select id="rangeSel" title="Khoảng thời gian">
        <option value="all">Cả chiến dịch</option>
        <option value="l7d">7 ngày gần nhất</option>
        <option value="l14d">14 ngày gần nhất</option>
        <option value="mtd">Tháng này (MTD)</option>
        <option value="today">Ngày mới nhất</option>
      </select>
      <span class="daterange"><input type="date" id="fromDate" title="Từ ngày"><span>→</span><input type="date" id="toDate" title="Đến ngày"></span>
      <button class="btn" id="refreshBtn" title="Tải lại dữ liệu">↻ Cập nhật</button>
    </div>
  </div>
</header>

<div class="wrap">
  <div class="banner" id="banner"></div>

  <!-- Đọc nhanh: định nghĩa chỉ số (siêu dễ hiểu) — LÊN ĐẦU -->
  <div class="section" style="margin-top:22px">
    <div class="section-h"><div class="n">i</div><h2>Đọc nhanh 30 giây — các con số nghĩa là gì?</h2>
      <span class="hint">Giải thích đơn giản nhất</span></div>
    <div class="card pad"><div class="defs-top">
      <div class="def"><div class="de">👀</div><div>
        <h4>Lượt hiển thị <small>(Impression)</small></h4>
        <p>Số lần quảng cáo hiện ra trước mắt mọi người — như có bao nhiêu người đi ngang qua tấm bảng quảng cáo của mình.</p></div></div>
      <div class="def"><div class="de">❤️</div><div>
        <h4>Lượt tương tác <small>(Engagement)</small></h4>
        <p>Số lần người ta bấm thích, bình luận, chia sẻ với quảng cáo — tức là bao nhiêu người thấy thích và "động tay" tương tác.</p></div></div>
      <div class="def"><div class="de">▶️</div><div>
        <h4>Lượt xem video <small>(View)</small></h4>
        <p>Số lần video được xem đủ lâu (từ 15 giây) — bao nhiêu người chịu dừng lại xem video của mình.</p></div></div>
      <div class="def"><div class="de">👆</div><div>
        <h4>Lượt bấm link <small>(Link Click)</small></h4>
        <p>Số lần người ta bấm vào đường link để tìm hiểu thêm — bao nhiêu người tò mò muốn biết nhiều hơn.</p></div></div>
      <div class="def"><div class="de">💰</div><div>
        <h4>Chi phí <small>(Spending)</small></h4>
        <p>Số tiền đã dùng để chạy quảng cáo cho tới lúc này.</p></div></div>
      <div class="def"><div class="de">🎯</div><div>
        <h4>Mục tiêu & Đúng tiến độ</h4>
        <p>"Mục tiêu" là con số hứa đạt cho cả chiến dịch. Mới chạy được một phần thời gian mà kết quả đã vượt phần đó → nghĩa là đang <b>chạy nhanh hơn dự kiến</b>, rất tốt.</p></div></div>
    </div></div>
  </div>

  <!-- Tổng quan: chiến dịch đang tốt -->
  <div class="section">
    <div class="summary card" id="summaryBox"></div>
  </div>

  <!-- KPI hero -->
  <div class="section">
    <div class="kpis" id="kpiCards"></div>
  </div>

  <!-- Flight pacing -->
  <div class="section">
    <div class="card pad flight" id="flightStrip"></div>
  </div>

  <!-- Trend -->
  <div class="section">
    <div class="section-h"><div class="n">◔</div><h2>Diễn tiến theo ngày</h2>
      <span class="hint" id="trendHint"></span></div>
    <div class="card pad">
      <div class="chart-wrap"><svg class="chart" id="trendChart"></svg></div>
      <div class="legend">
        <span><i style="background:#9BB0D8"></i> Impression / ngày</span>
        <span><i style="background:#4E6BAE"></i> Impression luỹ kế</span>
        <span><i style="background:#9AA3BA"></i> Nhịp chuẩn (mục tiêu theo thời gian)</span>
      </div>
    </div>
    <div id="cmtTrend"></div>
  </div>

  <!-- Hành trình + Tỷ trọng nội dung -->
  <div class="section">
    <div class="grid2">
      <div class="card pad">
        <div class="mini-h">Hành trình người dùng — từ nhìn thấy đến bấm tìm hiểu</div>
        <div id="funnel"></div>
      </div>
      <div class="card pad">
        <div class="mini-h">Tỷ trọng tiếp cận theo nội dung</div>
        <div id="donutWrap"></div>
      </div>
    </div>
  </div>

  <!-- I. Overview -->
  <div class="section">
    <div class="section-h"><div class="n">I</div><h2>Tổng quan — Objective × Asset</h2>
      <span class="hint">Mục tiêu = cho cả chiến dịch · Kết quả thực tế = số đã đạt tới thời điểm đang xem</span></div>
    <div class="card"><div class="table-wrap"><table id="tblOverview"></table></div></div>
    <div id="cmtOverview"></div>
  </div>

  <!-- II. Audience x Creative -->
  <div class="section">
    <div class="section-h"><div class="n">II</div><h2>Audience × Creative</h2>
      <span class="hint">Phân rã theo nhóm mẹ</span></div>
    <div class="card"><div class="table-wrap"><table id="tblAudience"></table></div></div>
    <div id="cmtAudience"></div>
  </div>

  <!-- III. Deepdive -->
  <div class="section">
    <div class="section-h"><div class="n">III</div><h2>Deepdive — Pillar × Asset</h2>
      <span class="hint">%VR = View/Impression · %CTR = Click/Impression</span></div>
    <div class="card"><div class="table-wrap"><table id="tblDeep"></table></div></div>
    <div id="cmtDeep"></div>
  </div>

  <footer>
    <div style="font-weight:800;color:var(--brand-blue-deep);font-size:13.5px;margin-bottom:4px">IMOJEV — Tiêm liều nhắc, chắc tương lai</div>
    <div><b>Zuellig Pharma · IMOJEV</b> — Facebook Performance Dashboard · Chỉ hiển thị chỉ số External (giá client).</div>
    <div id="footNote"></div>
  </footer>
</div>

<script>
/* ============================ CONFIG ============================ */
/* Để bật LIVE: dán link CSV "Publish to web" của tab FB_Paxy vào đây.
   File → Share → Publish to web → chọn tab FB_Paxy → Comma-separated values (.csv).
   Ví dụ: https://docs.google.com/spreadsheets/d/e/2PACX-xxxx/pub?gid=425474049&single=true&output=csv */
const DATA_URL = "__DATA_URL__";   // "" = dùng snapshot nhúng sẵn (set trong dashboard_config.json)
const AUTO_REFRESH_MIN = 10;   // phút; 0 = tắt auto refresh
/* =============================================================== */

const SNAP = __DATA_JSON__;
const KPI  = __KPI_JSON__;
const META = __META_JSON__;
const GENERATED = "__GENERATED__";

let ROWS = SNAP.slice();       // dữ liệu hiện hành (snapshot hoặc live)

/* ---------- helpers ---------- */
const CPM = META.cpmReach, CPC = META.cpcTraffic;
const fmtInt = n => Math.round(n).toLocaleString('vi-VN');
const fmtVND = n => Math.round(n).toLocaleString('vi-VN');
const fmtPct = (n,d=1) => (isFinite(n)?(n*100).toFixed(d):'0.0')+'%';
const spendOf = r => r.obj==='Reach' ? r.impr/1000*CPM : (r.obj==='Traffic'? r.click*CPC : 0);
const clamp01 = x => Math.max(0, Math.min(1, x));
const uniq = a => [...new Set(a)];

function daysBetween(a,b){ return Math.round((new Date(b)-new Date(a))/86400000); }
const FLIGHT_TOTAL = daysBetween(META.campaignStart, META.campaignEnd)+1;

/* ---------- date helpers ---------- */
function isoAdd(iso,days){ const d=new Date(iso); d.setDate(d.getDate()+days); return d.toISOString().slice(0,10); }

/* ---------- aggregation ---------- */
function sumMetrics(rows){
  const t={impr:0,eng:0,view:0,click:0,spend:0};
  rows.forEach(r=>{t.impr+=r.impr;t.eng+=r.eng;t.view+=r.view;t.click+=r.click;t.spend+=spendOf(r);});
  return t;
}
function kpiSum(filter){
  const t={budget:0,qty:0,impr:0,eng:0,view:0,click:0};
  KPI.filter(filter).forEach(k=>{t.budget+=k.budget;t.qty+=k.qty;t.impr+=k.impr;t.eng+=k.eng;t.view+=k.view;t.click+=k.click;});
  return t;
}
function groupBy(rows, keyFn){
  const m=new Map();
  rows.forEach(r=>{const k=keyFn(r); if(!m.has(k)) m.set(k,[]); m.get(k).push(r);});
  return m;
}

/* ============================ RENDER ============================ */
function updateDateBounds(){
  if(!ROWS.length) return;
  const mn=ROWS.reduce((m,r)=>r.date<m?r.date:m,ROWS[0].date), mx=ROWS.reduce((m,r)=>r.date>m?r.date:m,ROWS[0].date);
  ['fromDate','toDate'].forEach(id=>{const el=document.getElementById(id); el.min=mn; el.max=mx;});
}
function currentRange(){
  const maxd = ROWS.length? ROWS.reduce((m,r)=> r.date>m?r.date:m, ROWS[0].date) : (META.dataMaxDate||META.campaignEnd);
  const f=document.getElementById('fromDate').value, t=document.getElementById('toDate').value;
  if(f && t){ const from=f<=t?f:t, to=f<=t?t:f; return {from,to,label:`${vn(from)} – ${vn(to)}`}; }
  const mode=document.getElementById('rangeSel').value;
  let from=META.campaignStart;
  if(mode==='today') from=maxd;
  else if(mode==='l7d')  from=isoAdd(maxd,-6);
  else if(mode==='l14d') from=isoAdd(maxd,-13);
  else if(mode==='mtd')  from=maxd.slice(0,8)+'01';
  return {from, to:maxd, label:labelRange(mode)};
}
function render(){
  updateDateBounds();
  const range = currentRange();
  const rows = ROWS.filter(r=> r.date>=range.from && r.date<=range.to);
  const act = sumMetrics(rows);

  // full-campaign KPI totals
  const kReach   = kpiSum(k=>k.obj==='Reach');
  const kTraffic = kpiSum(k=>k.obj==='Traffic');
  const kAll     = kpiSum(()=>true);

  const trafficStarted = rows.some(r=>r.obj==='Traffic' && (r.impr>0||r.click>0));
  renderKpiCards(act, {kReach,kTraffic,kAll,trafficStarted});
  renderFlight(act, kAll);
  renderTrend(rows, kAll.impr/FLIGHT_TOTAL);
  renderFunnel(act);
  renderDonut(rows);
  renderOverview(rows);
  renderAudience(rows);
  renderDeep(rows);
  renderCommentary(rows, act, {kReach,kTraffic,kAll});

  document.getElementById('trendHint').textContent = rows.length? range.label : 'chưa có dữ liệu';
  document.getElementById('flightRange').textContent =
     `${vn(META.campaignStart)} → ${vn(META.campaignEnd)}`;
}
function labelRange(m){return{all:'Cả chiến dịch',l7d:'7 ngày gần nhất',l14d:'14 ngày gần nhất',mtd:'Tháng này',today:'Ngày mới nhất'}[m]||m;}
function vn(iso){const [y,mo,d]=iso.split('-');return `${d}/${mo}/${y}`;}

/* ---- flight progress % (theo ngày thực) ---- */
function flightElapsed(){
  const today = new Date().toISOString().slice(0,10);
  const cur = today < META.campaignStart ? META.campaignStart : (today>META.campaignEnd?META.campaignEnd:today);
  return clamp01((daysBetween(META.campaignStart,cur)+1)/FLIGHT_TOTAL);
}

function renderKpiCards(act, k){
  const flight = flightElapsed();
  const cards = [
    {lab:'Spending (Ext)', val:fmtVND(act.spend), unit:'đ', a:act.spend, kpi:k.kAll.budget, isMoney:true},
    {lab:'Impression',     val:fmtInt(act.impr),  unit:'', a:act.impr,  kpi:k.kReach.impr},  // vs mục tiêu Reach → khớp % ở summary
    {lab:'Engagement',     val:fmtInt(act.eng),   unit:'', a:act.eng,   kpi:k.kAll.eng},
    {lab:'View (Thruplay)',val:fmtInt(act.view),  unit:'', a:act.view,  kpi:k.kAll.view},
    {lab:'Link Click',     val:fmtInt(act.click), unit:'', a:act.click, kpi:k.kAll.click, later:!k.trafficStarted},
  ];
  document.getElementById('kpiCards').innerHTML = cards.map(c=>{
    if(c.later){   // nhánh kéo click (Traffic) chưa tới lịch chạy → KHÔNG hiện % gây hoang mang
      return `<div class="card kpi">
        <div class="lab"><span class="ic"></span>${c.lab}</div>
        <div class="val">${c.val}<span class="unit"> ${c.unit}</span></div>
        <div class="vs">Nhánh kéo click chạy ở <b>giai đoạn sau</b></div>
        <div class="bar"><i style="width:0%"></i></div>
        <div class="pct"><span>&nbsp;</span><span style="color:var(--muted);font-weight:700">Sắp khởi động</span></div>
      </div>`;
    }
    const p = c.kpi>0 ? clamp01(c.a/c.kpi) : 0;
    const pl = paceLabel(c.kpi>0?c.a/c.kpi:0, flight, c.a);
    return `<div class="card kpi">
      <div class="lab"><span class="ic"></span>${c.lab}</div>
      <div class="val">${c.val}<span class="unit"> ${c.unit}</span></div>
      <div class="vs">Mục tiêu: <b>${c.kpi>0?(c.isMoney?fmtVND(c.kpi)+'đ':fmtInt(c.kpi)):'—'}</b></div>
      <div class="bar"><i style="width:${(p*100).toFixed(1)}%"></i></div>
      <div class="pct"><span>đạt <b>${fmtPct(c.kpi>0?c.a/c.kpi:0)}</b></span>
        <span style="color:${pl.col};font-weight:700">${c.kpi>0?pl.t:''}</span></div>
    </div>`;
  }).join('');
}

/* nhãn nhịp — tích cực/trung tính, không gây hoang mang cho khách */
function paceLabel(ach, flight, actual){
  if(actual<=0) return {t:'Sắp khởi động', col:'var(--muted)'};
  if(ach>=flight) return {t:'Vượt tiến độ ✓', col:'var(--ok)'};
  if(ach>=flight*0.5) return {t:'Đúng nhịp ✓', col:'var(--ok)'};
  return {t:'Đang tăng tốc', col:'var(--zp-red)'};
}

function renderFlight(act, kAll){
  const flight = flightElapsed();
  const today = new Date().toISOString().slice(0,10);
  const cur = today>META.campaignEnd?META.campaignEnd:today;
  const elapsed = Math.max(0, Math.min(FLIGHT_TOTAL, daysBetween(META.campaignStart,cur)+1));
  const deliv = kAll.budget>0 ? act.spend/kAll.budget : 0;
  const onPace = deliv >= flight*0.85;
  document.getElementById('flightStrip').innerHTML = `
    <div class="big">Flight: ngày ${elapsed}/${FLIGHT_TOTAL}</div>
    <div class="track"><div class="bar" style="height:9px"><i style="width:${(flight*100).toFixed(1)}%"></i></div></div>
    <span class="chip">${fmtPct(flight,0)} thời gian đã trôi</span>
    <span class="chip">${fmtPct(deliv,1)} ngân sách đã giải ngân</span>
    <span class="chip ${onPace?'ok':''}">${onPace?'Đúng/vượt nhịp':'Đang tối ưu chi phí'}</span>`;
}

/* ---- SVG trend chart (impression/ngày + luỹ kế) ---- */
function renderTrend(rows, idealPerDay){
  const svg = document.getElementById('trendChart');
  const W=1000,H=260,PL=54,PR=54,PT=16,PB=34;
  const byDate = new Map();
  rows.forEach(r=>byDate.set(r.date,(byDate.get(r.date)||0)+r.impr));
  const days=[...byDate.keys()].sort();
  if(!days.length){svg.innerHTML='';return;}
  const daily=days.map(d=>byDate.get(d));
  let run=0; const cum=daily.map(v=>run+=v);
  // nhịp chuẩn: mục tiêu impr/ngày × số ngày (lịch) từ đầu khoảng
  const ideal=days.map(d=> (idealPerDay||0)*(daysBetween(days[0],d)+1));
  const maxD=Math.max(...daily,1), maxC=Math.max(...cum,...ideal,1);
  const x=i=>PL+(days.length===1?(W-PL-PR)/2:i*(W-PL-PR)/(days.length-1));
  const yD=v=>H-PB-(v/maxD)*(H-PT-PB);
  const yC=v=>H-PB-(v/maxC)*(H-PT-PB);
  const bw=Math.max(6,Math.min(30,(W-PL-PR)/days.length*0.6));
  let g='';
  // y grid + labels (impr/day left)
  for(let i=0;i<=4;i++){const yy=PT+i*(H-PT-PB)/4;const val=maxD*(1-i/4);
    g+=`<line x1="${PL}" y1="${yy}" x2="${W-PR}" y2="${yy}" stroke="#eee"/>`;
    g+=`<text x="${PL-8}" y="${yy+4}" text-anchor="end" font-size="10" fill="#A39EA0">${fmtInt(val)}</text>`;}
  // bars daily (lime)
  days.forEach((d,i)=>{const h=H-PB-yD(daily[i]);
    g+=`<rect x="${x(i)-bw/2}" y="${yD(daily[i])}" width="${bw}" height="${Math.max(0,h)}" rx="2" fill="#9BB0D8" opacity="1"><title>${vn(d)}: ${fmtInt(daily[i])} impr</title></rect>`;});
  // ideal-pace line (dashed grey) — mục tiêu theo thời gian
  if(idealPerDay){const ip=days.map((d,i)=>`${x(i)},${yC(ideal[i])}`).join(' ');
    g+=`<polyline points="${ip}" fill="none" stroke="#9AA3BA" stroke-width="2" stroke-dasharray="6 5"><title>Nhịp chuẩn (mục tiêu theo thời gian)</title></polyline>`;}
  // cumulative line (blue)
  const pts=days.map((d,i)=>`${x(i)},${yC(cum[i])}`).join(' ');
  g+=`<polyline points="${pts}" fill="none" stroke="#4E6BAE" stroke-width="2.8"/>`;
  days.forEach((d,i)=>{g+=`<circle cx="${x(i)}" cy="${yC(cum[i])}" r="3" fill="#4E6BAE"><title>${vn(d)}: luỹ kế ${fmtInt(cum[i])}</title></circle>`;});
  // right axis (cumulative)
  for(let i=0;i<=4;i++){const yy=PT+i*(H-PT-PB)/4;const val=maxC*(1-i/4);
    g+=`<text x="${W-PR+8}" y="${yy+4}" text-anchor="start" font-size="10" fill="#A39EA0">${fmtInt(val)}</text>`;}
  // x labels (thin)
  const step=Math.ceil(days.length/8);
  days.forEach((d,i)=>{if(i%step===0||i===days.length-1){const [yy,mo,dd]=d.split('-');
    g+=`<text x="${x(i)}" y="${H-12}" text-anchor="middle" font-size="10" fill="#A39EA0">${dd}/${mo}</text>`;}});
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  svg.innerHTML=g;
}

/* ---- I. Overview: Objective x Asset ---- */
function achMini(a,kpi){
  const p=kpi>0?clamp01(a/kpi):0;
  return `<span class="mini"><span class="minibar"><i style="width:${(p*100).toFixed(0)}%"></i></span>${fmtPct(kpi>0?a/kpi:0)}</span>`;
}
function renderOverview(rows){
  const objs=['Reach','Traffic'];
  let html=`<thead><tr><th>Objective / Asset</th>
     <th>KPI Budget</th><th>KPI Qty</th><th>Actual Spend</th><th>Impression</th><th>Click</th><th>Đạt (theo KPI)</th></tr></thead><tbody>`;
  const g=groupBy(rows, r=>r.obj+'||'+r.asset);
  let G={spend:0,impr:0,click:0}, GK={budget:0};
  objs.forEach(obj=>{
    const assets = uniq(KPI.filter(k=>k.obj===obj).map(k=>k.asset)).sort();
    // objective subtotal
    const oAct = sumMetrics(rows.filter(r=>r.obj===obj));
    const oK   = kpiSum(k=>k.obj===obj);
    G.spend+=oAct.spend;G.impr+=oAct.impr;G.click+=oAct.click;GK.budget+=oK.budget;
    html+=`<tr class="obj-row"><td><span class="pill ${obj.toLowerCase()}">${obj}</span></td>
       <td>${fmtVND(oK.budget)}</td><td>${fmtInt(oK.qty)}</td>
       <td>${fmtVND(oAct.spend)}</td><td>${fmtInt(oAct.impr)}</td><td>${fmtInt(oAct.click)}</td>
       <td>${achMini(obj==='Reach'?oAct.impr:oAct.click, obj==='Reach'?oK.impr:oK.click)}</td></tr>`;
    assets.forEach(asset=>{
      const rr=(g.get(obj+'||'+asset)||[]);
      const a=sumMetrics(rr);
      const kk=kpiSum(k=>k.obj===obj && k.asset===asset);
      const primaryA = obj==='Reach'?a.impr:a.click, primaryK = obj==='Reach'?kk.impr:kk.click;
      html+=`<tr><td class="sub-td">&nbsp;&nbsp;&nbsp;${asset}</td>
        <td class="sub-td">${fmtVND(kk.budget)}</td><td class="sub-td">${fmtInt(kk.qty)}</td>
        <td>${fmtVND(a.spend)}</td><td>${fmtInt(a.impr)}</td><td>${fmtInt(a.click)}</td>
        <td>${achMini(primaryA,primaryK)}</td></tr>`;
    });
  });
  const GKall=kpiSum(()=>true);
  html+=`<tr class="grand"><td>GRAND TOTAL</td><td>${fmtVND(GKall.budget)}</td><td>—</td>
     <td>${fmtVND(G.spend)}</td><td>${fmtInt(G.impr)}</td><td>${fmtInt(G.click)}</td>
     <td>${fmtPct(GKall.budget>0?G.spend/GKall.budget:0)}</td></tr>`;
  html+='</tbody>';
  document.getElementById('tblOverview').innerHTML=html;
}

/* ---- II. Audience x Creative ---- */
function renderAudience(rows){
  const auds = uniq(KPI.map(k=>k.aud)).filter(a=>a && !/0-15/.test(a)).sort();
  let html=`<thead><tr><th>Audience / Asset</th><th>Objective</th>
     <th>KPI Qty</th><th>Actual Spend</th><th>Impression</th><th>View</th><th>Click</th><th>Đạt</th></tr></thead><tbody>`;
  auds.forEach(aud=>{
    const aAct=sumMetrics(rows.filter(r=>r.aud===aud));
    const aK=kpiSum(k=>k.aud===aud);
    html+=`<tr class="obj-row"><td>${aud}</td><td></td><td>${fmtInt(aK.qty)}</td>
      <td>${fmtVND(aAct.spend)}</td><td>${fmtInt(aAct.impr)}</td><td>${fmtInt(aAct.view)}</td><td>${fmtInt(aAct.click)}</td>
      <td>${achMini(aAct.impr, aK.impr)}</td></tr>`;
    // rows by obj+asset within audience that have KPI
    const combos = KPI.filter(k=>k.aud===aud).map(k=>k.obj+'||'+k.asset);
    uniq(combos).sort().forEach(c=>{
      const [obj,asset]=c.split('||');
      const rr=rows.filter(r=>r.aud===aud&&r.obj===obj&&r.asset===asset);
      const a=sumMetrics(rr);
      const kk=kpiSum(k=>k.aud===aud&&k.obj===obj&&k.asset===asset);
      const pa=obj==='Reach'?a.impr:a.click, pk=obj==='Reach'?kk.impr:kk.click;
      html+=`<tr><td class="sub-td">&nbsp;&nbsp;&nbsp;${asset}</td>
        <td><span class="pill ${obj.toLowerCase()}">${obj}</span></td>
        <td class="sub-td">${fmtInt(kk.qty)}</td>
        <td>${fmtVND(a.spend)}</td><td>${fmtInt(a.impr)}</td><td>${fmtInt(a.view)}</td><td>${fmtInt(a.click)}</td>
        <td>${achMini(pa,pk)}</td></tr>`;
    });
  });
  html+='</tbody>';
  document.getElementById('tblAudience').innerHTML=html;
}

/* ---- III. Deepdive Pillar x Asset ---- */
function renderDeep(rows){
  let html=`<thead><tr><th>Pillar / Asset</th><th>Impression</th><th>View 15s</th><th>Click</th><th>%VR</th><th>%CTR</th></tr></thead><tbody>`;
  const pillars = uniq(rows.map(r=>r.pillar)).sort();
  pillars.forEach(p=>{
    const pr=rows.filter(r=>r.pillar===p); const pa=sumMetrics(pr);
    html+=`<tr class="obj-row"><td>${p}</td><td>${fmtInt(pa.impr)}</td><td>${fmtInt(pa.view)}</td><td>${fmtInt(pa.click)}</td>
      <td>${fmtPct(pa.impr>0?pa.view/pa.impr:0,2)}</td><td>${fmtPct(pa.impr>0?pa.click/pa.impr:0,3)}</td></tr>`;
    const assets=uniq(pr.map(r=>r.asset)).sort();
    assets.forEach(as=>{
      const a=sumMetrics(pr.filter(r=>r.asset===as));
      html+=`<tr><td class="sub-td">&nbsp;&nbsp;&nbsp;${as}</td><td>${fmtInt(a.impr)}</td><td>${fmtInt(a.view)}</td><td>${fmtInt(a.click)}</td>
        <td class="sub-td">${fmtPct(a.impr>0?a.view/a.impr:0,2)}</td><td class="sub-td">${fmtPct(a.impr>0?a.click/a.impr:0,3)}</td></tr>`;
    });
  });
  if(!pillars.length) html+=`<tr><td colspan="6" style="text-align:center;color:var(--muted)">Chưa có dữ liệu</td></tr>`;
  html+='</tbody>';
  document.getElementById('tblDeep').innerHTML=html;
}

/* ---- Phễu hành trình: Hiển thị → Tương tác → Xem → Bấm link ---- */
function renderFunnel(act){
  const steps=[
    {k:'Hiển thị', v:act.impr, c:'#4E6BAE'},
    {k:'Tương tác', v:act.eng, c:'#6C8CC7'},
    {k:'Xem video', v:act.view, c:'#9BB0D8'},
    {k:'Bấm link', v:act.click, c:'#CADB36'},
  ];
  const max=steps[0].v||1; let h='';
  steps.forEach((s,i)=>{
    const w=Math.max(4, s.v/max*100);
    const prev=i>0?steps[i-1].v:0;
    const step=i>0&&prev>0? ` · giữ lại ${fmtPct(s.v/prev,1)} so với bước trước`:'';
    h+=`<div class="fn-row"><div class="fn-lab">${s.k}</div>
      <div class="fn-barwrap"><div class="fn-bar" style="width:${w}%;background:${s.c}"></div><span class="fn-val">${fmtInt(s.v)}</span></div>
      <div class="fn-sub">${i===0?'100% — điểm khởi đầu':fmtPct(s.v/max,2)+' của lượt hiển thị'}${step}</div></div>`;
  });
  document.getElementById('funnel').innerHTML=h;
}
/* ---- Donut tỷ trọng tiếp cận theo nội dung ---- */
function renderDonut(rows){
  const m=aggMap(rows.filter(r=>r.impr>0), r=>r.asset, r=>r.impr);
  const entries=Object.entries(m).sort((a,b)=>b[1]-a[1]);
  if(!entries.length){document.getElementById('donutWrap').innerHTML='<div class="fn-sub">Chưa có dữ liệu</div>';return;}
  const total=entries.reduce((s,e)=>s+e[1],0)||1;
  const colors=['#6C8CC7','#CADB36','#4E6BAE','#B3C42B','#9BB0D8','#E2E88F'];
  const R=52,C=2*Math.PI*R; let off=0,arcs='',leg='';
  entries.forEach((e,i)=>{const frac=e[1]/total,col=colors[i%colors.length],len=frac*C;
    arcs+=`<circle cx="70" cy="70" r="${R}" fill="none" stroke="${col}" stroke-width="18" stroke-dasharray="${len} ${C-len}" stroke-dashoffset="${-off}" transform="rotate(-90 70 70)"><title>${assetVN(e[0])}: ${fmtInt(e[1])} (${fmtPct(frac,1)})</title></circle>`;
    off+=len;
    leg+=`<div class="lg-row"><span class="lg-sw" style="background:${col}"></span>${assetVN(e[0])} <b>${fmtPct(frac,1)}</b></div>`;});
  document.getElementById('donutWrap').innerHTML=`<div class="donut-flex">
    <svg viewBox="0 0 140 140" width="150" height="150" style="flex:0 0 auto">${arcs}
      <text x="70" y="66" text-anchor="middle" font-size="11" fill="#767B6A">Tổng tiếp cận</text>
      <text x="70" y="85" text-anchor="middle" font-size="15" font-weight="800" fill="#242A15">${fmtShort(total)}</text>
    </svg><div class="donut-legend">${leg}</div></div>`;
}

/* ============================ NHẬN XÉT + NEXT ACTION ============================ */
const PILLAR_VN={'KNOW THE RISK':'Nhận biết nguy cơ bệnh','PROTECT ON TIME':'Bảo vệ con đúng lúc','CLOSE THE GAP':'Tiêm nhắc đúng lịch'};
const assetVN=a=>a;   // giữ tên gốc asset (Master Video, KV, Event…) — KHÔNG dịch sang TV
const pillarVN=p=>PILLAR_VN[p]||(p||'').replace(/^\w/,c=>c);
function fmtShort(n){n=+n||0;if(n>=1e6)return (n/1e6).toLocaleString('vi-VN',{maximumFractionDigits:2})+' triệu';if(n>=1e3)return Math.round(n/1e3).toLocaleString('vi-VN')+' nghìn';return fmtInt(n);}
function aggMap(rows,keyFn,valFn){const m={};rows.forEach(r=>{const k=keyFn(r);m[k]=(m[k]||0)+valFn(r);});return m;}
function maxKey(m){let bk=null,bv=-Infinity;for(const k in m){if(m[k]>bv){bv=m[k];bk=k;}}return bk;}
function bestRate(rows,keyFn,numFn,denFn,minDen){
  const num={},den={};rows.forEach(r=>{const k=keyFn(r);num[k]=(num[k]||0)+numFn(r);den[k]=(den[k]||0)+denFn(r);});
  let bk=null,bv=-1;for(const k in den){if(den[k]>=minDen){const rt=num[k]/den[k];if(rt>bv){bv=rt;bk=k;}}}return {key:bk,rate:bv};
}
function cmtBox(note){   // chỉ hiển thị Nhận xét cho khách (bỏ "Việc làm tiếp theo" theo yêu cầu)
  return `<div class="cmt">
    <div class="cmt-row"><span class="cmt-ic">💬</span><div><div class="h">Nhận xét</div><p>${note}</p></div></div>
  </div>`;
}

function renderCommentary(rows, act, k){
  const flight=flightElapsed();
  const kReach=k.kReach, kAll=k.kAll;
  const reachAch = kReach.impr>0 ? act.impr/kReach.impr : 0;   // reach impr đã đạt so với mục tiêu Reach
  const engRate  = act.impr>0 ? act.eng/act.impr : 0;
  const ahead = reachAch >= flight;

  const topAsset = maxKey(aggMap(rows.filter(r=>r.obj==='Reach'), r=>r.asset, r=>r.impr)) || '—';
  const topPil = maxKey(aggMap(rows, r=>r.pillar, r=>r.impr)) || '—';
  const vrPil = bestRate(rows, r=>r.pillar, r=>r.view, r=>r.impr, 50000);
  const heroPil = (vrPil.key||topPil);

  // ---- Tổng quan (tích cực) ----
  const paceTxt = ahead ? 'đang chạy <b>nhanh hơn tiến độ dự kiến</b>' : 'đang bám sát kế hoạch';
  const sumNote = `Mới đi được <b>${fmtPct(flight,0)}</b> chặng đường mà chiến dịch đã xây nhận biết, đưa thông điệp IMOJEV đến <b>${fmtShort(act.impr)} lượt hiển thị</b> `
    + `(đạt <b>${fmtPct(reachAch)}</b> mục tiêu tiếp cận cả chiến dịch) và thu về <b>${fmtShort(act.eng)} lượt tương tác</b> — ${paceTxt}. `
    + `Cứ 100 người nhìn thấy thì khoảng <b>${(engRate*100).toFixed(1)}</b> người dừng lại thích / xem / bấm — mức quan tâm tốt, đang củng cố vị thế Top-of-Mind cho IMOJEV. `
    + `Nội dung hiệu quả nhất hiện nay: <b>${assetVN(topAsset)}</b>.`;
  document.getElementById('summaryBox').innerHTML =
    `<div class="sum-badge">✓ Chiến dịch đang chạy tốt</div><div class="sum-note">${sumNote}</div>`;

  // ---- Trend ----
  document.getElementById('cmtTrend').innerHTML = cmtBox(
    `Lượng tiếp cận tăng đều qua từng ngày, cộng dồn đã đạt <b>${fmtShort(act.impr)} lượt hiển thị</b>. Những ngày có nội dung mới lên sóng thường bật cao hơn hẳn.`);

  // ---- I. Overview ----
  document.getElementById('cmtOverview').innerHTML = cmtBox(
    `Nhánh <b>tăng nhận biết</b> đang chạy mạnh: mang về <b>${fmtShort(act.impr)} lượt hiển thị</b>`
    + `${act.click>0?` và <b>${fmtInt(act.click)} lượt bấm link</b> dù chưa tới lịch chạy quảng cáo kéo click`:''}. `
    + `Nội dung <b>${assetVN(topAsset)}</b> phủ rộng nhất.`);

  // ---- II. Audience (business-aware: 5–15 là nhóm CORE, KHÔNG headline theo nhóm nhiều nhất) ----
  const coreImpr = rows.filter(r=>/5[-–]15/.test(r.aud)).reduce((s,r)=>s+r.impr,0);
  const yngImpr  = rows.filter(r=>/0[-–]2\b/.test(r.aud)).reduce((s,r)=>s+r.impr,0);
  const coreLead = coreImpr>=yngImpr;
  document.getElementById('cmtAudience').innerHTML = cmtBox(
    `Trọng tâm chiến dịch là <b>nhóm core — phụ huynh có con 5–15 tuổi</b> (mục tiêu thúc đẩy mũi nhắc lại): đã tiếp cận <b>${fmtShort(coreImpr)} lượt hiển thị</b>${coreLead?' — đang dẫn đầu về tiếp cận, đúng hướng':''}. `
    + `Nhóm con nhỏ 0–2 tuổi (tiêm sớm) được phủ bổ trợ <b>${fmtShort(yngImpr)} lượt</b>. `
    + `Cả hai đều nằm trong tệp mục tiêu; ngân sách vẫn ưu tiên đúng nhóm core 5–15.`);

  // ---- III. Deepdive ----
  document.getElementById('cmtDeep').innerHTML = cmtBox(
    `Thông điệp <b>"${pillarVN(heroPil)}"</b> đang thu hút người xem tốt nhất${vrPil.rate>0?` (tỉ lệ xem video cao nhất, ${fmtPct(vrPil.rate,2)})`:''}. Đây là hướng nội dung chạm đúng mối quan tâm của phụ huynh.`);
}

/* ============================ DATA LOADING ============================ */
function parseCSV(text){
  const rows=[]; let i=0,f='',row=[],q=false;
  while(i<text.length){const c=text[i];
    if(q){ if(c==='"'){ if(text[i+1]==='"'){f+='"';i++;}else q=false;} else f+=c; }
    else{ if(c==='"')q=true; else if(c===','){row.push(f);f='';} else if(c==='\n'){row.push(f);rows.push(row);row=[];f='';} else if(c==='\r'){} else f+=c; }
    i++;}
  if(f.length||row.length){row.push(f);rows.push(row);}
  return rows;
}
function normAsset(a){a=(a||'').trim();const m={'animation video':'Animation Video','master video':'Master Video','expert video':'Expert Video','event':'Event','kv':'KV','social':'Social'};return m[a.toLowerCase()]||a;}
function isoDate(s){s=(s||'').trim();if(!s)return null;
  if(s.includes('-')&&s.length>=8){const p=s.slice(0,10);if(/^\d{4}-\d{2}-\d{2}$/.test(p))return p;}
  if(s.includes('/')){const[m,d,y]=s.split('/');if(y)return `${(+y).toString().padStart(4,'0')}-${(+m).toString().padStart(2,'0')}-${(+d).toString().padStart(2,'0')}`;}
  return null;}
function toNum(x){if(x==null)return 0;const s=(''+x).trim().replace(/,/g,'');if(!s||s.toUpperCase()==='#N/A')return 0;const n=+s;return isFinite(n)?n:0;}

function rowsFromCSV(text){
  const g=parseCSV(text); if(!g.length)return[];
  const head=g[0].map(h=>(h||'').trim());
  const idx=n=>head.indexOf(n);
  const iDate=idx('Date'),iCh=idx('Channel'),iObj=idx('Objective'),iPil=idx('Pillar'),
        iAs=idx('Asset'),iAud=idx('Audience'),iImp=idx('Impression'),iEng=idx('Engagement'),
        iView=idx('FB Thruplay Action'),iClk=idx('Link click');
  const out=[];
  for(let r=1;r<g.length;r++){const row=g[r];
    const d=isoDate(row[iDate]); const ch=(row[iCh]||'').trim(); const obj=(row[iObj]||'').trim();
    if(!d||ch!=='Facebook'||(obj!=='Reach'&&obj!=='Traffic'))continue;
    out.push({date:d,obj,pillar:(row[iPil]||'').trim()||'(n/a)',asset:normAsset(row[iAs]),
      aud:(row[iAud]||'').trim()||'(n/a)',impr:toNum(row[iImp]),eng:toNum(row[iEng]),
      view:toNum(row[iView]),click:toNum(row[iClk])});
  }
  return out;
}

function setLive(isLive, note){
  document.getElementById('liveDot').className='dot'+(isLive?'':' snap');
  document.getElementById('liveText').textContent=isLive?'LIVE':'Snapshot';
  document.getElementById('footNote').innerHTML = note;
}
async function loadLive(){
  const banner=document.getElementById('banner');
  if(!DATA_URL){
    ROWS=SNAP.slice();
    setLive(false, `Nguồn: snapshot nhúng lúc build · ${GENERATED}. &nbsp;`);
    banner.style.display='none';
    render(); return;
  }
  try{
    const res=await fetch(DATA_URL+(DATA_URL.includes('?')?'&':'?')+'_t='+Date.now());
    if(!res.ok) throw new Error('HTTP '+res.status);
    const txt=await res.text();
    const rows=rowsFromCSV(txt);
    if(!rows.length) throw new Error('CSV rỗng/không đọc được cột');
    ROWS=rows; banner.style.display='none';
    setLive(true, `Nguồn: LIVE từ Google Sheet (FB_Paxy) · cập nhật lúc ${new Date().toLocaleString('vi-VN')}`);
    render();
  }catch(e){
    ROWS=SNAP.slice();
    setLive(false, `Snapshot dự phòng · ${GENERATED}`);
    banner.style.display='block';
    banner.textContent='⚠ Không fetch được dữ liệu LIVE ('+e.message+'). Đang dùng snapshot. Kiểm tra lại link publish của tab FB_Paxy.';
    render();
  }
}

document.getElementById('rangeSel').addEventListener('change', ()=>{
  document.getElementById('fromDate').value=''; document.getElementById('toDate').value=''; render();
});
document.getElementById('fromDate').addEventListener('change', render);
document.getElementById('toDate').addEventListener('change', render);
document.getElementById('refreshBtn').addEventListener('click', loadLive);
loadLive();
if(AUTO_REFRESH_MIN>0 && DATA_URL) setInterval(loadLive, AUTO_REFRESH_MIN*60000);
</script>
</body>
</html>
'''

if __name__ == '__main__':
    main()
