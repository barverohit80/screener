import os
import json
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

# =====================================================================
# CONFIGURATION
# =====================================================================
DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
DATA_DIR = os.path.join(DOCS_DIR, "data")

def get_db_engine():
    if not DB_CONNECTION_STRING:
        print("❌ Error: DB_CONNECTION_STRING environment variable is not set.")
        return None
    try:
        return create_engine(DB_CONNECTION_STRING)
    except Exception as e:
        print(f"Error creating DB engine: {e}")
        return None

def safe_float(val, default=0.0):
    if val is None or pd.isna(val):
        return default
    if isinstance(val, (int, float)):
        return float(val)
    try:
        s = str(val).strip().replace(',', '').replace('%', '')
        if not s or s == '-':
            return default
        return float(s)
    except (ValueError, TypeError):
        return default

def safe_int(val, default=0):
    if val is None or pd.isna(val):
        return default
    if isinstance(val, (int, float)):
        return int(val)
    try:
        s = str(val).strip().replace(',', '')
        if not s or s == '-':
            return default
        return int(float(s))
    except (ValueError, TypeError):
        return default

def export_ep_calendar_json():
    """
    Exports EP breakout data and D+1 performance tracking into JSON 
    formatted for the GitHub Pages Calendar UI.
    """
    engine = get_db_engine()
    if not engine:
        return

    cutoff_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    print(f"🚀 Exporting EP Calendar Data for GitHub Pages UI (since {cutoff_date})...")
    
    try:
        with engine.connect() as conn:
            ep_query = text(f'SELECT * FROM "episodicPivot" WHERE "DATE" >= \'{cutoff_date}\' ORDER BY "DATE" DESC')
            ep_df = pd.read_sql(ep_query, conn)

            bhav_query = text(f'SELECT "SYMBOL", "DATE", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME" FROM bhavcopies WHERE "DATE" >= \'{cutoff_date}\'')
            bhav_df = pd.read_sql(bhav_query, conn)
    except Exception as e:
        print(f"❌ Error fetching from DB: {e}")
        return

    if ep_df.empty:
        print("⚠️ No EP data found.")
        return

    bhav_df['DATE'] = pd.to_datetime(bhav_df['DATE']).dt.tz_localize(None)
    ep_df['DATE'] = pd.to_datetime(ep_df['DATE']).dt.tz_localize(None)

    # Build D+1 lookup table
    d1_lookup = {}
    for idx, row in ep_df.iterrows():
        sym = row['SYMBOL']
        ep_date = row['DATE']
        ep_date_str = ep_date.strftime('%Y-%m-%d')
        key = f"{sym}_{ep_date_str}"
        ep_close = safe_float(row.get('CLOSE'))
        ep_prev = safe_float(row.get('PREV'), ep_close)
        ep_gain_rs = ep_close - ep_prev

        sub = bhav_df[(bhav_df['SYMBOL'] == sym) & (bhav_df['DATE'] > ep_date)].sort_values('DATE')
        if not sub.empty:
            d1_row = sub.iloc[0]
            d1_date_str = d1_row['DATE'].strftime('%Y-%m-%d')
            d1_open = safe_float(d1_row.get('OPEN'))
            d1_high = safe_float(d1_row.get('HIGH'))
            d1_low = safe_float(d1_row.get('LOW'))
            d1_close = safe_float(d1_row.get('CLOSE'))
            
            d1_retained_gain_rs = round(d1_close - ep_prev, 2)
            d1_retained_gain_pct = round((d1_retained_gain_rs / ep_gain_rs) * 100, 2) if ep_gain_rs > 0 else 100.0
            d1_return_pct = round(((d1_close - ep_close) / ep_close) * 100, 2) if ep_close > 0 else 0.0

            if d1_retained_gain_pct < 95.0 or d1_return_pct < -5.0:
                status = 'RED'
            elif d1_retained_gain_pct >= 96.0 or d1_close >= ep_close:
                status = 'GREEN'
            else:
                status = 'YELLOW'

            d1_lookup[key] = {
                'd1_date': d1_date_str,
                'd1_open': d1_open,
                'd1_high': d1_high,
                'd1_low': d1_low,
                'd1_close': d1_close,
                'd1_return_pct': d1_return_pct,
                'd1_retained_gain_pct': d1_retained_gain_pct,
                'status': status
            }
        else:
            d1_lookup[key] = {
                'd1_date': 'N/A',
                'd1_open': None,
                'd1_high': None,
                'd1_low': None,
                'd1_close': None,
                'd1_return_pct': None,
                'd1_retained_gain_pct': None,
                'status': 'PENDING'
            }

    # Group EPs by Date
    calendar_data = {}
    
    for date_val, group in ep_df.groupby('DATE'):
        date_str = date_val.strftime('%Y-%m-%d')
        ep_list = []
        
        for idx, row in group.iterrows():
            sym = row['SYMBOL']
            key = f"{sym}_{date_str}"
            d1_info = d1_lookup.get(key, {'status': 'PENDING'})

            ep_list.append({
                'symbol': sym,
                'prev_close': safe_float(row.get('PREV', 0)),
                'open_price': safe_float(row.get('OPEN', 0)),
                'high_price': safe_float(row.get('HIGH', 0)),
                'low_price': safe_float(row.get('LOW', 0)),
                'close': safe_float(row.get('CLOSE', 0)),
                'change_pct': safe_float(row.get('Price_Change_%', 0)),
                'vol_ratio': safe_float(row.get('Vol_Ratio', 0)),
                'volume': safe_int(row.get('VOLUME', 0)),
                'sma_vol_50': safe_float(row.get('SMA_Vol_50', 0)),
                'deliv_qty': safe_int(row.get('DELIV_QTY', 0)),
                'deliv_per': safe_float(row.get('DELIV_PER', 0)),
                'turnover_lacs': safe_float(row.get('TURNOVER_LACS', 0)),
                'deliv_trend': str(row.get('Deliv_Trend', 'NEW')),
                'weekday': str(row.get('Weekday', '')),
                'd1_date': d1_info.get('d1_date'),
                'd1_open': d1_info.get('d1_open'),
                'd1_high': d1_info.get('d1_high'),
                'd1_low': d1_info.get('d1_low'),
                'd1_close': d1_info.get('d1_close'),
                'd1_return_pct': d1_info.get('d1_return_pct'),
                'd1_retained_gain_pct': d1_info.get('d1_retained_gain_pct'),
                'd1_status': d1_info.get('status')
            })

        calendar_data[date_str] = {
            'date': date_str,
            'count': len(ep_list),
            'ep_list': ep_list
        }

    # Create output directory
    os.makedirs(DATA_DIR, exist_ok=True)
    json_path = os.path.join(DATA_DIR, "ep_calendar_data.json")

    output_payload = {
        'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S IST'),
        'total_dates': len(calendar_data),
        'total_eps': len(ep_df),
        'calendar': calendar_data
    }

    with open(json_path, 'w') as f:
        json.dump(output_payload, f, indent=2)

    print(f"✅ Generated JSON file: {json_path} ({len(calendar_data)} dates, {len(ep_df)} EPs)")
    return json_path

if __name__ == "__main__":
    export_ep_calendar_json()
