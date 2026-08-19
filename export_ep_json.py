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
    Exports 4 presentation tables (New, Persistent, Sustained, Fizzled)
    and full calendar breakdown into JSON for GitHub Pages.
    """
    engine = get_db_engine()
    if not engine:
        return

    cutoff_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    print(f"🚀 Exporting 4-Table EP Analysis & Calendar Data (since {cutoff_date})...")
    
    try:
        with engine.connect() as conn:
            ep_query = text(f'SELECT * FROM "episodicPivot" WHERE "DATE" >= \'{cutoff_date}\' ORDER BY "DATE" DESC')
            ep_df = pd.read_sql(ep_query, conn)

            bhav_query = text(f'SELECT "SYMBOL", "DATE", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME", "DELIV_QTY", "DELIV_PER" FROM bhavcopies WHERE "DATE" >= \'{cutoff_date}\' ORDER BY "DATE" ASC')
            bhav_df = pd.read_sql(bhav_query, conn)
    except Exception as e:
        print(f"❌ Error fetching from DB: {e}")
        return

    if ep_df.empty:
        print("⚠️ No EP data found.")
        return

    bhav_df['DATE'] = pd.to_datetime(bhav_df['DATE']).dt.tz_localize(None)
    ep_df['DATE'] = pd.to_datetime(ep_df['DATE']).dt.tz_localize(None)

    # 1. Identify Latest Market & EP Dates
    latest_market_date_val = bhav_df['DATE'].max() if not bhav_df.empty else ep_df['DATE'].max()
    latest_market_date_str = latest_market_date_val.strftime('%Y-%m-%d') if pd.notna(latest_market_date_val) else 'N/A'
    
    global_latest_ep_date = ep_df['DATE'].max()
    global_latest_ep_date_str = global_latest_ep_date.strftime('%Y-%m-%d')

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

    # 2. Build 50-Day Trajectory for Every Symbol
    # Filter 50-day window
    window_50d = (latest_market_date_val - timedelta(days=70))
    ep_50d_df = ep_df[ep_df['DATE'] >= window_50d].copy()
    
    unique_symbols = ep_50d_df['SYMBOL'].unique()
    
    new_eps_list = []
    persistent_eps_list = []
    sustained_eps_list = []
    fizzled_eps_list = []
    
    for sym in unique_symbols:
        sym_eps = ep_50d_df[ep_50d_df['SYMBOL'] == sym].sort_values('DATE')
        sym_bhav = bhav_df[bhav_df['SYMBOL'] == sym].sort_values('DATE')
        
        if sym_eps.empty:
            continue
            
        first_ep = sym_eps.iloc[0]
        latest_ep = sym_eps.iloc[-1]
        latest_bhav = sym_bhav.iloc[-1] if not sym_bhav.empty else None
        
        ep1_date_str = first_ep['DATE'].strftime('%Y-%m-%d')
        ep1_prev = safe_float(first_ep.get('PREV'))
        ep1_open = safe_float(first_ep.get('OPEN'))
        ep1_high = safe_float(first_ep.get('HIGH'))
        ep1_low = safe_float(first_ep.get('LOW'))
        ep1_close = safe_float(first_ep.get('CLOSE'))
        ep1_change_pct = safe_float(first_ep.get('Price_Change_%'))
        ep1_vol_ratio = safe_float(first_ep.get('Vol_Ratio'))
        ep1_volume = safe_int(first_ep.get('VOLUME'))
        ep1_sma_vol = safe_float(first_ep.get('SMA_Vol_50'))
        ep1_deliv_per = safe_float(first_ep.get('DELIV_PER'))
        ep1_gain_rs = round(ep1_close - ep1_prev, 2)
        
        latest_ep_date_str = latest_ep['DATE'].strftime('%Y-%m-%d')
        latest_ep_prev = safe_float(latest_ep.get('PREV'))
        latest_ep_open = safe_float(latest_ep.get('OPEN'))
        latest_ep_high = safe_float(latest_ep.get('HIGH'))
        latest_ep_low = safe_float(latest_ep.get('LOW'))
        latest_ep_close = safe_float(latest_ep.get('CLOSE'))
        latest_ep_change_pct = safe_float(latest_ep.get('Price_Change_%'))
        latest_ep_vol_ratio = safe_float(latest_ep.get('Vol_Ratio'))
        latest_ep_volume = safe_int(latest_ep.get('VOLUME'))
        latest_ep_sma_vol = safe_float(latest_ep.get('SMA_Vol_50'))
        latest_ep_deliv_per = safe_float(latest_ep.get('DELIV_PER'))
        latest_deliv_trend = str(latest_ep.get('Deliv_Trend', 'NEW'))
        
        appearance_count = len(sym_eps)
        ep_history_dates = [d.strftime('%Y-%m-%d') for d in sym_eps['DATE']]
        
        current_date_str = latest_bhav['DATE'].strftime('%Y-%m-%d') if latest_bhav is not None else latest_market_date_str
        current_price = safe_float(latest_bhav.get('CLOSE')) if latest_bhav is not None else latest_ep_close
        
        # Max High and Low since 1st EP
        post_ep1_bhav = sym_bhav[sym_bhav['DATE'] >= first_ep['DATE']]
        max_high_since_ep1 = safe_float(post_ep1_bhav['HIGH'].max()) if not post_ep1_bhav.empty else ep1_close
        min_low_since_ep1 = safe_float(post_ep1_bhav['LOW'].min()) if not post_ep1_bhav.empty else ep1_close
        days_since_ep1 = len(post_ep1_bhav)
        
        # Returns vs 1st EP
        current_return_since_ep1_pct = round(((current_price - ep1_close) / ep1_close) * 100, 2) if ep1_close > 0 else 0.0
        current_gain_from_base_rs = round(current_price - ep1_prev, 2)
        retained_ep1_gain_pct = round((current_gain_from_base_rs / ep1_gain_rs) * 100, 2) if ep1_gain_rs > 0 else 100.0
        gain_lost_pct = round(100.0 - retained_ep1_gain_pct, 2)
        
        # D+1 lookup for 1st EP & Latest EP
        key_ep1 = f"{sym}_{ep1_date_str}"
        key_latest = f"{sym}_{latest_ep_date_str}"
        d1_info_ep1 = d1_lookup.get(key_ep1, {'status': 'PENDING'})
        d1_info_latest = d1_lookup.get(key_latest, {'status': 'PENDING'})
        
        record = {
            'symbol': sym,
            'appearance_count': appearance_count,
            'ep_history_dates': ep_history_dates,
            'ep1_date': ep1_date_str,
            'ep1_prev': ep1_prev,
            'ep1_open': ep1_open,
            'ep1_high': ep1_high,
            'ep1_low': ep1_low,
            'ep1_close': ep1_close,
            'ep1_change_pct': ep1_change_pct,
            'ep1_vol_ratio': ep1_vol_ratio,
            'ep1_volume': ep1_volume,
            'ep1_sma_vol': ep1_sma_vol,
            'ep1_deliv_per': ep1_deliv_per,
            'latest_ep_date': latest_ep_date_str,
            'latest_ep_prev': latest_ep_prev,
            'latest_ep_open': latest_ep_open,
            'latest_ep_high': latest_ep_high,
            'latest_ep_low': latest_ep_low,
            'latest_ep_close': latest_ep_close,
            'latest_ep_change_pct': latest_ep_change_pct,
            'latest_ep_vol_ratio': latest_ep_vol_ratio,
            'latest_ep_volume': latest_ep_volume,
            'latest_ep_sma_vol': latest_ep_sma_vol,
            'latest_ep_deliv_per': latest_ep_deliv_per,
            'latest_deliv_trend': latest_deliv_trend,
            'current_price': current_price,
            'current_date': current_date_str,
            'max_high_since_ep1': max_high_since_ep1,
            'min_low_since_ep1': min_low_since_ep1,
            'days_since_ep1': days_since_ep1,
            'current_return_since_ep1_pct': current_return_since_ep1_pct,
            'retained_ep1_gain_pct': retained_ep1_gain_pct,
            'gain_lost_pct': gain_lost_pct,
            'd1_status_ep1': d1_info_ep1.get('status', 'PENDING'),
            'd1_status_latest': d1_info_latest.get('status', 'PENDING')
        }
        
        # ─── 1. TABLE 1: TODAY'S / NEW EPISODIC PIVOTS ───
        # Criteria: Triggered an Episodic Pivot on the latest market session (both fresh and repeat breakouts)
        if latest_ep['DATE'] == global_latest_ep_date:
            new_eps_list.append(record)
            
        # ─── 2. TABLE 2: PERSISTENT EPISODIC PIVOTS ───
        # Criteria: Appeared >= 2 times in the last 50 days
        if appearance_count >= 2:
            persistent_eps_list.append(record)
            
        # ─── 3. TABLE 3: SUSTAINED EPISODIC PIVOTS ───
        # Criteria: Current price holds above 1st EP close (or retained gain >= 96%)
        if current_price >= ep1_close:
            sustained_eps_list.append(record)
            
        # ─── 4. TABLE 4: FIZZLED OUT EPISODIC PIVOTS ───
        # Criteria: Current price dropped below 1st EP Prev Close (entire EP day gain vanished)
        if current_price < ep1_prev:
            fizzled_eps_list.append(record)

    # Sort each list logically
    new_eps_list.sort(key=lambda x: x['latest_ep_change_pct'], reverse=True)
    persistent_eps_list.sort(key=lambda x: (x['appearance_count'], x['current_return_since_ep1_pct']), reverse=True)
    sustained_eps_list.sort(key=lambda x: x['current_return_since_ep1_pct'], reverse=True)
    fizzled_eps_list.sort(key=lambda x: x['current_return_since_ep1_pct']) # Most negative first

    # 3. Group Calendar Data by Date
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

    # 4. Create Output Payload
    os.makedirs(DATA_DIR, exist_ok=True)
    json_path = os.path.join(DATA_DIR, "ep_calendar_data.json")

    output_payload = {
        'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S IST'),
        'latest_market_date': latest_market_date_str,
        'latest_ep_date': global_latest_ep_date_str,
        'total_dates': len(calendar_data),
        'total_eps_overall': len(ep_df),
        'total_eps_50d': len(ep_50d_df),
        'summary': {
            'new_count': len(new_eps_list),
            'persistent_count': len(persistent_eps_list),
            'sustained_count': len(sustained_eps_list),
            'fizzled_count': len(fizzled_eps_list),
            'sustained_rate_pct': round((len(sustained_eps_list) / len(unique_symbols)) * 100, 1) if len(unique_symbols) > 0 else 0.0,
            'fizzled_rate_pct': round((len(fizzled_eps_list) / len(unique_symbols)) * 100, 1) if len(unique_symbols) > 0 else 0.0
        },
        'tables': {
            'new_eps': new_eps_list,
            'persistent_eps': persistent_eps_list,
            'sustained_eps': sustained_eps_list,
            'fizzled_eps': fizzled_eps_list
        },
        'calendar': calendar_data
    }

    with open(json_path, 'w') as f:
        json.dump(output_payload, f, indent=2)

    print(f"\n📊 4-Table Summary Exported:")
    print(f"   • 🌟 New EPs ({global_latest_ep_date_str}): {len(new_eps_list)}")
    print(f"   • 🔁 Persistent (>=2 Hits): {len(persistent_eps_list)}")
    print(f"   • 🚀 Sustained (Holding Gains Above EP1): {len(sustained_eps_list)}")
    print(f"   • 💨 Fizzled Out (Gains Vanished Below Base): {len(fizzled_eps_list)}")
    print(f"✅ Generated JSON file: {json_path}")
    return json_path

if __name__ == "__main__":
    export_ep_calendar_json()
