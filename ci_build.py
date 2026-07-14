# -*- coding: utf-8 -*-
"""
CI build cho GitHub Actions (Linux) — KHÔNG phụ thuộc path Windows.
Đọc FB_Paxy + KPI RAW qua Google Sheets API (credentials lấy từ ENV secrets),
rồi sinh docs/index.html DÙNG CHUNG TEMPLATE + helper của build_dashboard.py.

ENV cần:
  GOOGLE_TOKEN   = toàn bộ nội dung token.json  (bắt buộc; chứa refresh_token)
  GOOGLE_CLIENT  = nội dung oauth_client.json    (tuỳ chọn; chỉ cần nếu token.json thiếu client_id/secret)
  ZP_SHEET_ID    = (tuỳ chọn) id sheet, mặc định = sheet EXT Zuellig
  ZP_OUT         = (tuỳ chọn) file output, mặc định docs/index.html
"""
import os, sys, io, json, datetime, time, socket
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
socket.setdefaulttimeout(90)   # tránh treo request; kết hợp with_retry chống timeout mạng

def with_retry(fn, tries=4, delay=8):
    """Thử lại khi mạng chập chờn (TimeoutError / lỗi tạm thời khi gọi Google API)."""
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            if i == tries - 1:
                raise
            print(f'[retry {i+1}/{tries}] {type(e).__name__}: {e}', flush=True)
            time.sleep(delay)

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build as gbuild

import build_dashboard as bd   # tái dùng TEMPLATE, norm_asset, to_num, iso_date, hằng số

SHEET_ID = os.environ.get('ZP_SHEET_ID', '16AtdH_bp5cN9wGG1t7qmmfdTfNlevY7vVZ9TQ-qrHnY')
# Meta Ads breakdown (Region/Placement/Age) nằm ở sheet INT — chỉ đọc 3 tab report (KHÔNG đụng cột chi phí)
INT_SHEET_ID = os.environ.get('ZP_INT_SHEET_ID', '1Ddc4vjylCCnVCYaor5iXE6rgOc-ZIWH86xA0vxu6Jow')
OUT = os.environ.get('ZP_OUT', 'docs/index.html')
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']


def creds_from_env():
    tok = json.loads(os.environ['GOOGLE_TOKEN'])
    info = dict(tok)
    if not info.get('client_id') or not info.get('client_secret'):
        cli = json.loads(os.environ.get('GOOGLE_CLIENT') or '{}')
        c = cli.get('installed') or cli.get('web') or {}
        info.setdefault('client_id', c.get('client_id'))
        info.setdefault('client_secret', c.get('client_secret'))
        info.setdefault('token_uri', c.get('token_uri', 'https://oauth2.googleapis.com/token'))
    info.setdefault('token_uri', 'https://oauth2.googleapis.com/token')
    # dùng đúng scope đã được cấp trong token (tránh invalid_scope khi refresh)
    creds = Credentials.from_authorized_user_info(info, info.get('scopes'))
    if not creds.valid:
        creds.refresh(Request())
    return creds


def _dicts(values):
    if not values:
        return []
    head = [(h or '').strip() for h in values[0]]
    out = []
    for r in values[1:]:
        out.append({head[i]: (r[i] if i < len(r) else '') for i in range(len(head))})
    return out


def load_paxy(svc):
    vals = svc.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range='FB_Paxy!A1:AH5000').execute().get('values', [])
    rows = []
    for rec in _dicts(vals):
        d = bd.iso_date(rec.get('Date'))
        ch = (rec.get('Channel') or '').strip()
        obj = (rec.get('Objective') or '').strip()
        if not d or ch != 'Facebook' or obj not in ('Reach', 'Traffic'):
            continue
        rows.append({
            'date': d, 'obj': obj,
            'pillar': (rec.get('Pillar') or '').strip() or '(n/a)',
            'asset': bd.norm_asset(rec.get('Asset')),
            'aud': (rec.get('Audience') or '').strip() or '(n/a)',
            'impr': bd.to_num(rec.get('Impression')), 'eng': bd.to_num(rec.get('Engagement')),
            'view': bd.to_num(rec.get('FB Thruplay Action')), 'click': bd.to_num(rec.get('Link click')),
        })
    return rows


def load_kpi(svc):
    vals = svc.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range="'KPI RAW'!A1:X5000").execute().get('values', [])
    agg = {}
    for rec in _dicts(vals):
        ch = (rec.get('Channel') or '').strip()
        obj = (rec.get('Objective') or '').strip()
        if ch != 'Facebook' or obj not in ('Reach', 'Traffic'):
            continue
        asset = bd.norm_asset(rec.get('Asset'))
        aud = (rec.get('Audience') or '').strip()
        a = agg.setdefault((obj, asset, aud), {'obj': obj, 'asset': asset, 'aud': aud,
            'budget': 0.0, 'qty': 0.0, 'impr': 0.0, 'eng': 0.0, 'view': 0.0, 'click': 0.0})
        a['budget'] += bd.to_num(rec.get('KPI Budget')); a['qty'] += bd.to_num(rec.get('KPI_Quantity'))
        a['impr'] += bd.to_num(rec.get('KPI_Impression')); a['eng'] += bd.to_num(rec.get('KPI_Engagement'))
        a['view'] += bd.to_num(rec.get('KPI_View')); a['click'] += bd.to_num(rec.get('KPI_Click'))
    return list(agg.values())


def load_pool(svc):
    vals = svc.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range='Reach!A1:C50').execute().get('values', [])
    rows = []
    for r in vals[1:]:
        if not r or not (r[0] or '').strip():
            continue
        rows.append({'name': r[0].strip(),
                     'pool': bd.to_num(r[1]) if len(r) > 1 else 0,
                     'reach': bd.to_num(r[2]) if len(r) > 2 else 0})
    if not rows:
        rows = [{'name': 'Mẹ có con 0–15 tuổi', 'pool': 20250000, 'reach': 0},
                {'name': 'Mẹ có con 0–2 tuổi', 'pool': 13800000, 'reach': 0}]
    return rows


def load_report(svc):
    """Đọc 3 tab Meta breakdown từ sheet INT → aggregate (reuse bd.aggregate_report).
    Bọc try/except: thiếu tab / mất quyền thì bỏ qua (dashboard vẫn build, chỉ ẩn Section IV)."""
    def rd(rng):
        try:
            vals = svc.spreadsheets().values().get(
                spreadsheetId=INT_SHEET_ID, range=rng).execute().get('values', [])
            return _dicts(vals)
        except Exception as e:
            print(f'[report] bỏ qua {rng}: {type(e).__name__}: {e}', flush=True)
            return []
    def rd_grid(rng):                       # RAW values (list-of-lists) cho pivot Age+Gender
        try:
            return svc.spreadsheets().values().get(
                spreadsheetId=INT_SHEET_ID, range=rng).execute().get('values', [])
        except Exception as e:
            print(f'[report] bỏ qua {rng}: {type(e).__name__}: {e}', flush=True)
            return []
    r3 = rd("'Raw Data Report (3)'!A1:J300")
    r4 = rd("'Raw Data Report (4)'!A1:J300")
    r5 = rd("'Raw Data Report (5)'!A1:J300")
    rweek = rd("'Freq by week'!A1:Z200")        # tab tần suất theo tuần (nếu có) → chart; thiếu tab thì []
    rag = rd_grid("'Age + Gender'!A1:Q40")      # pivot Age+Gender (nửa phải tab) → khối Age & Gender
    return bd.aggregate_report(r3, r4, r5, rweek, rag)


def main():
    def _fetch():
        svc = gbuild('sheets', 'v4', credentials=creds_from_env())
        return svc, load_paxy(svc), load_kpi(svc), load_pool(svc), load_report(svc)
    svc, paxy, kpi, pool, report = with_retry(_fetch)
    dates = sorted({r['date'] for r in paxy})
    meta = {'cpmReach': bd.CPM_REACH, 'cpcTraffic': bd.CPC_TRAFFIC,
            'campaignStart': bd.CAMPAIGN_START, 'campaignEnd': bd.CAMPAIGN_END,
            'dataMinDate': dates[0] if dates else None, 'dataMaxDate': dates[-1] if dates else None,
            'nRows': len(paxy)}
    # giờ VN (UTC+7) cho dễ đọc
    gen = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime('%Y-%m-%d %H:%M') + ' (giờ VN)'

    html = bd.TEMPLATE
    html = html.replace('__DATA_JSON__', json.dumps(paxy, ensure_ascii=False))
    html = html.replace('__KPI_JSON__', json.dumps(kpi, ensure_ascii=False))
    html = html.replace('__META_JSON__', json.dumps(meta, ensure_ascii=False))
    html = html.replace('__POOL_JSON__', json.dumps(pool, ensure_ascii=False))
    html = html.replace('__REPORT_JSON__', json.dumps(report, ensure_ascii=False))
    html = html.replace('__DATA_URL__', '')     # bản CI = bake snapshot mỗi lần chạy (không cần live-fetch)
    html = html.replace('__GENERATED__', gen)

    os.makedirs(os.path.dirname(OUT) or '.', exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(html)
    tot = sum(r['impr'] for r in paxy)
    rep = (f'report[reg={len(report["region"])} plc={len(report["placement"])} age={len(report["age"])}] '
           f'win={report["window"]["start"]}..{report["window"]["end"]}') if report.get('hasData') else 'report=none'
    print(f'[OK] {OUT} | rows={len(paxy)} | dates={meta["dataMinDate"]}..{meta["dataMaxDate"]} '
          f'| impr={tot:,.0f} | kpi_combos={len(kpi)} | {rep} | {gen}')


if __name__ == '__main__':
    main()
