import os
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
import requests
from dotenv import load_dotenv
from telegram_notifier import send_telegram_document

load_dotenv()

# =====================================================================
# CONFIGURATION
# =====================================================================
DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DAILY_SCREENER_DIR = os.getenv("DAILY_SCREENER_DIR", os.path.join(BASE_DIR, "output"))

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

def run_ep_d1_performance_tracker(days_back=70):
    """
    Tracks D+1 performance for all Episodic Pivot stocks from the last 50+ days.
    
    Criteria:
    - GREEN: Max pullback on D+1 is <= 4.0% (Holding gain)
    - RED: Fell by > 5.0% on D+1 (Failed/Weak move)
    - YELLOW: Moderate pullback (between 4.0% and 5.0%)
    - PENDING: D+1 trading session has not occurred yet
    """
    engine = get_db_engine()
    if not engine:
        return None

    print("\n" + "═"*60)
    print("      EPISODIC PIVOT D+1 PERFORMANCE TRACKER      ")
    print("═"*60 + "\n")

    cutoff_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    print(f"Fetching EP records and Bhavcopies from DB (since {cutoff_date})...")

    try:
        with engine.connect() as conn:
            ep_query = text(f'SELECT * FROM "episodicPivot" WHERE "DATE" >= \'{cutoff_date}\' ORDER BY "DATE" DESC')
            ep_df = pd.read_sql(ep_query, conn)

            bhav_query = text(f'SELECT "SYMBOL", "DATE", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME", "DELIV_QTY" FROM bhavcopies WHERE "DATE" >= \'{cutoff_date}\'')
            bhav_df = pd.read_sql(bhav_query, conn)
    except Exception as e:
        print(f"❌ Database error: {e}")
        return None

    if ep_df.empty:
        print("⚠️ No EP records found in database for the specified date range.")
        return None

    bhav_df['DATE'] = pd.to_datetime(bhav_df['DATE']).dt.tz_localize(None)
    ep_df['DATE'] = pd.to_datetime(ep_df['DATE']).dt.tz_localize(None)

    results = []
    for idx, row in ep_df.iterrows():
        sym = row['SYMBOL']
        ep_date = row['DATE']
        ep_date_str = ep_date.strftime('%Y-%m-%d')
        ep_close = safe_float(row.get('CLOSE'))
        ep_prev = safe_float(row.get('PREV'), ep_close)
        ep_gain_rs = round(ep_close - ep_prev, 2)
        ep_change_pct = safe_float(row.get('Price_Change_%', 0))
        vol_ratio = safe_float(row.get('Vol_Ratio', 0))

        # Query subsequent trading sessions for this symbol
        sub = bhav_df[(bhav_df['SYMBOL'] == sym) & (bhav_df['DATE'] > ep_date)].sort_values('DATE')

        if not sub.empty:
            d1_row = sub.iloc[0]
            d1_date_str = d1_row['DATE'].strftime('%Y-%m-%d')
            d1_open = safe_float(d1_row.get('OPEN'))
            d1_high = safe_float(d1_row.get('HIGH'))
            d1_low = safe_float(d1_row.get('LOW'))
            d1_close = safe_float(d1_row.get('CLOSE'))
            d1_volume = safe_int(d1_row.get('VOLUME'))

            # Retained EP Gain calculation based on EP Prev (Day T-1) and D+1 Close (Day T+1)
            d1_retained_gain_rs = round(d1_close - ep_prev, 2)
            d1_retained_gain_pct = round((d1_retained_gain_rs / ep_gain_rs) * 100, 2) if ep_gain_rs > 0 else 100.0
            
            d1_low_retained_rs = round(d1_low - ep_prev, 2)
            d1_low_retained_gain_pct = round((d1_low_retained_rs / ep_gain_rs) * 100, 2) if ep_gain_rs > 0 else 100.0
            
            d1_return_pct = round(((d1_close - ep_close) / ep_close) * 100, 2) if ep_close > 0 else 0.0

            # Rule:
            # GREEN: Retains >= 96.0% of EP Day Gain (or D1_Close >= EP_Close)
            # RED: Retains < 95.0% of EP Day Gain (or D1_Return < -5.0%)
            # YELLOW: Retains between 95.0% and 96.0% of EP Day Gain
            if d1_retained_gain_pct < 95.0 or d1_return_pct < -5.0:
                status = 'RED'
                remarks = f"RED: Retained only {d1_retained_gain_pct}% of EP Gain on D+1 Close"
            elif d1_retained_gain_pct >= 96.0 or d1_close >= ep_close:
                status = 'GREEN'
                remarks = f"GREEN: Retained {d1_retained_gain_pct}% of EP Gain on D+1 Close"
            else:
                status = 'YELLOW'
                remarks = f"YELLOW: Retained between 95% and 96% of EP Gain ({d1_retained_gain_pct}%)"
        else:
            d1_date_str = 'N/A'
            d1_open = None
            d1_high = None
            d1_low = None
            d1_close = None
            d1_volume = None
            d1_return_pct = None
            d1_retained_gain_rs = None
            d1_retained_gain_pct = None
            d1_low_retained_gain_pct = None
            status = 'PENDING'
            remarks = 'Awaiting D+1 Session'

        results.append({
            'SYMBOL': sym,
            'EP_Date': ep_date_str,
            'EP_Prev_Close': ep_prev,
            'EP_Close': ep_close,
            'EP_Day_Gain_Rs': ep_gain_rs,
            'EP_Gain_%': ep_change_pct,
            'EP_Vol_Ratio': vol_ratio,
            'D1_Date': d1_date_str,
            'D1_Open': d1_open,
            'D1_High': d1_high,
            'D1_Low': d1_low,
            'D1_Close': d1_close,
            'D1_Return_%': d1_return_pct,
            'D1_Retained_EP_Gain_Rs': d1_retained_gain_rs,
            'D1_Retained_EP_Gain_%': d1_retained_gain_pct,
            'D1_Low_Retained_EP_Gain_%': d1_low_retained_gain_pct,
            'Status': status,
            'Remarks': remarks
        })

    res_df = pd.DataFrame(results)

    # 4-Category Multi-Day Aggregation
    latest_ep_date = ep_df['DATE'].max()
    unique_symbols = ep_df['SYMBOL'].unique()

    new_eps_records = []
    persistent_records = []
    sustained_records = []
    fizzled_records = []

    for sym in unique_symbols:
        sym_eps = ep_df[ep_df['SYMBOL'] == sym].sort_values('DATE')
        sym_bhav = bhav_df[bhav_df['SYMBOL'] == sym].sort_values('DATE')
        
        if sym_eps.empty:
            continue
            
        first_ep = sym_eps.iloc[0]
        latest_ep = sym_eps.iloc[-1]
        latest_bhav = sym_bhav.iloc[-1] if not sym_bhav.empty else None

        ep1_date_str = first_ep['DATE'].strftime('%Y-%m-%d')
        ep1_prev = safe_float(first_ep.get('PREV'))
        ep1_close = safe_float(first_ep.get('CLOSE'))
        ep1_gain_rs = round(ep1_close - ep1_prev, 2)

        latest_ep_date_str = latest_ep['DATE'].strftime('%Y-%m-%d')
        latest_ep_close = safe_float(latest_ep.get('CLOSE'))
        appearance_count = len(sym_eps)

        current_price = safe_float(latest_bhav.get('CLOSE')) if latest_bhav is not None else latest_ep_close
        current_return_since_ep1_pct = round(((current_price - ep1_close) / ep1_close) * 100, 2) if ep1_close > 0 else 0.0
        current_gain_from_base_rs = round(current_price - ep1_prev, 2)
        retained_ep1_gain_pct = round((current_gain_from_base_rs / ep1_gain_rs) * 100, 2) if ep1_gain_rs > 0 else 100.0
        gain_lost_pct = round(100.0 - retained_ep1_gain_pct, 2)

        post_ep1_bhav = sym_bhav[sym_bhav['DATE'] >= first_ep['DATE']]
        max_high_since_ep1 = safe_float(post_ep1_bhav['HIGH'].max()) if not post_ep1_bhav.empty else ep1_close

        base_dict = {
            'SYMBOL': sym,
            'Appearance_Count_50d': appearance_count,
            '1st_EP_Date': ep1_date_str,
            '1st_EP_Base_PrevClose': ep1_prev,
            '1st_EP_Close': ep1_close,
            '1st_EP_Change_%': safe_float(first_ep.get('Price_Change_%')),
            'Latest_EP_Date': latest_ep_date_str,
            'Latest_EP_Close': latest_ep_close,
            'Current_Price': current_price,
            'Current_Return_Since_EP1_%': current_return_since_ep1_pct,
            'Retained_EP1_Gain_%': retained_ep1_gain_pct,
            'Gain_Lost_%': gain_lost_pct,
            'Max_High_Since_EP1': max_high_since_ep1,
            'Days_Active': len(post_ep1_bhav)
        }

        # 1. Today's EPs: Latest EP date (both fresh and repeat breakouts)
        if latest_ep['DATE'] == latest_ep_date:
            new_eps_records.append(base_dict)

        # 2. Persistent EPs: >= 2 hits in 50 days
        if appearance_count >= 2:
            persistent_records.append(base_dict)

        # 3. Sustained EPs: Current price >= 1st EP close
        if current_price >= ep1_close:
            sustained_records.append(base_dict)

        # 4. Fizzled Out EPs: Current price < 1st EP Prev Close
        if current_price < ep1_prev:
            fizzled_records.append(base_dict)

    new_eps_df = pd.DataFrame(new_eps_records)
    persistent_df = pd.DataFrame(persistent_records)
    sustained_df = pd.DataFrame(sustained_records)
    fizzled_df = pd.DataFrame(fizzled_records)

    total_tracked_symbols = len(unique_symbols)
    sustained_pct = f"{(len(sustained_df)/total_tracked_symbols*100):.1f}%" if total_tracked_symbols > 0 else '0%'
    fizzled_pct = f"{(len(fizzled_df)/total_tracked_symbols*100):.1f}%" if total_tracked_symbols > 0 else '0%'

    print(f"\n📊 4-Category Performance Summary (Last 50 Days):")
    print(f"   • 🌟 Table 1: New EPs (Latest: {latest_ep_date.strftime('%Y-%m-%d')}): {len(new_eps_df)}")
    print(f"   • 🔁 Table 2: Persistent (≥2 Hits): {len(persistent_df)}")
    print(f"   • 🚀 Table 3: Sustained (Holding Above EP1): {len(sustained_df)} ({sustained_pct})")
    print(f"   • 💨 Table 4: Fizzled Out (Gains Vanished): {len(fizzled_df)} ({fizzled_pct})")

    # Export Multi-Sheet Excel Workbook
    os.makedirs(DAILY_SCREENER_DIR, exist_ok=True)
    excel_path = os.path.join(DAILY_SCREENER_DIR, "ep_d1_performance_50days.xlsx")

    summary_rows = [
        {'Category': 'Total Unique EP Stocks (50d)', 'Count / Metric': total_tracked_symbols},
        {'Category': '1. New EPs (Latest Session)', 'Count / Metric': len(new_eps_df)},
        {'Category': '2. Persistent EPs (≥2 Hits)', 'Count / Metric': len(persistent_df)},
        {'Category': '3. Sustained EPs (Holding Gains)', 'Count / Metric': f"{len(sustained_df)} ({sustained_pct})"},
        {'Category': '4. Fizzled Out EPs (Gains Lost)', 'Count / Metric': f"{len(fizzled_df)} ({fizzled_pct})"},
        {'Category': 'Total EP Signals Evaluated', 'Count / Metric': len(res_df)}
    ]
    summary_df = pd.DataFrame(summary_rows)

    with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
        summary_df.to_excel(writer, sheet_name='Summary Stats', index=False)
        if not new_eps_df.empty:
            new_eps_df.to_excel(writer, sheet_name='1_New_EPs', index=False)
        if not persistent_df.empty:
            persistent_df.to_excel(writer, sheet_name='2_Persistent_EPs', index=False)
        if not sustained_df.empty:
            sustained_df.to_excel(writer, sheet_name='3_Sustained_EPs', index=False)
        if not fizzled_df.empty:
            fizzled_df.to_excel(writer, sheet_name='4_Fizzled_EPs', index=False)
        res_df.to_excel(writer, sheet_name='All D+1 Raw Tracking', index=False)

    print(f"\n✅ Saved Excel report: {excel_path}")

    # Dispatch to Telegram
    caption = (
        f"📊 *Episodic Pivot 4-Category Performance Report*\n\n"
        f"🌟 *1. New EPs ({latest_ep_date.strftime('%d-%b-%Y')})*: {len(new_eps_df)}\n"
        f"🔁 *2. Persistent EPs (≥2 Hits in 50d)*: {len(persistent_df)}\n"
        f"🚀 *3. Sustained EPs (Holding Above EP1)*: {len(sustained_df)} ({sustained_pct})\n"
        f"💨 *4. Fizzled Out EPs (Gains Vanished)*: {len(fizzled_df)} ({fizzled_pct})\n\n"
        f"📁 _Attached full Excel workbook with all 4 sheets._"
    )
    send_telegram_document(excel_path, caption=caption)

    return res_df

if __name__ == "__main__":
    run_ep_d1_performance_tracker()
