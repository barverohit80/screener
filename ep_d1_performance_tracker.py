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

    bhav_df['DATE'] = pd.to_datetime(bhav_df['DATE'])
    ep_df['DATE'] = pd.to_datetime(ep_df['DATE'])

    results = []
    for idx, row in ep_df.iterrows():
        sym = row['SYMBOL']
        ep_date = row['DATE']
        ep_date_str = ep_date.strftime('%Y-%m-%d')
        ep_close = float(row['CLOSE'])
        ep_change_pct = float(row.get('Price_Change_%', 0))
        vol_ratio = float(row.get('Vol_Ratio', 0))

        # Query subsequent trading sessions for this symbol
        sub = bhav_df[(bhav_df['SYMBOL'] == sym) & (bhav_df['DATE'] > ep_date)].sort_values('DATE')

        if not sub.empty:
            d1_row = sub.iloc[0]
            d1_date_str = d1_row['DATE'].strftime('%Y-%m-%d')
            d1_open = float(d1_row['OPEN'])
            d1_high = float(d1_row['HIGH'])
            d1_low = float(d1_row['LOW'])
            d1_close = float(d1_row['CLOSE'])
            d1_volume = int(d1_row['VOLUME'])

            d1_return_pct = round(((d1_close - ep_close) / ep_close) * 100, 2)
            d1_max_pullback_pct = round(((ep_close - d1_low) / ep_close) * 100, 2)

            # Evaluate D+1 Status
            if d1_max_pullback_pct > 5.0 or d1_return_pct < -5.0:
                status = 'RED'
                remarks = f"Fell >5% on D+1 (Max Pullback: {d1_max_pullback_pct}%)"
            elif d1_max_pullback_pct <= 4.0 and d1_return_pct >= -4.0:
                status = 'GREEN'
                remarks = f"Held gain (Max Pullback: {d1_max_pullback_pct}%)"
            else:
                status = 'YELLOW'
                remarks = f"Moderate Pullback ({d1_max_pullback_pct}%)"
        else:
            d1_date_str = 'N/A'
            d1_open = None
            d1_high = None
            d1_low = None
            d1_close = None
            d1_volume = None
            d1_return_pct = None
            d1_max_pullback_pct = None
            status = 'PENDING'
            remarks = 'Awaiting D+1 Session'

        results.append({
            'SYMBOL': sym,
            'EP_Date': ep_date_str,
            'EP_Close': ep_close,
            'EP_Gain_%': ep_change_pct,
            'EP_Vol_Ratio': vol_ratio,
            'D1_Date': d1_date_str,
            'D1_Open': d1_open,
            'D1_High': d1_high,
            'D1_Low': d1_low,
            'D1_Close': d1_close,
            'D1_Return_%': d1_return_pct,
            'D1_Max_Pullback_%': d1_max_pullback_pct,
            'Status': status,
            'Remarks': remarks
        })

    res_df = pd.DataFrame(results)

    # Calculate Summary Statistics
    total_eps = len(res_df)
    green_df = res_df[res_df['Status'] == 'GREEN']
    red_df = res_df[res_df['Status'] == 'RED']
    yellow_df = res_df[res_df['Status'] == 'YELLOW']
    pending_df = res_df[res_df['Status'] == 'PENDING']

    print(f"📊 Summary (Last 50+ Days EP D+1 Tracking):")
    print(f"   • Total EPs Tracked: {total_eps}")
    print(f"   • GREEN (Holding Gain, <=4% Pullback): {len(green_df)} ({len(green_df)/total_eps*100:.1f}%)")
    print(f"   • RED (Fell > 5%): {len(red_df)} ({len(red_df)/total_eps*100:.1f}%)")
    print(f"   • YELLOW (Moderate Pullback 4-5%): {len(yellow_df)} ({len(yellow_df)/total_eps*100:.1f}%)")
    print(f"   • PENDING (Awaiting D+1 Session): {len(pending_df)}")

    # Export Multi-Sheet Excel Workbook
    os.makedirs(DAILY_SCREENER_DIR, exist_ok=True)
    excel_path = os.path.join(DAILY_SCREENER_DIR, "ep_d1_performance_50days.xlsx")

    summary_rows = [
        {'Metric': 'Total EPs Tracked', 'Value': total_eps},
        {'Metric': 'GREEN Count (Hold <= 4%)', 'Value': len(green_df)},
        {'Metric': 'GREEN %', 'Value': f"{len(green_df)/total_eps*100:.1f}%" if total_eps > 0 else '0%'},
        {'Metric': 'RED Count (Fell > 5%)', 'Value': len(red_df)},
        {'Metric': 'RED %', 'Value': f"{len(red_df)/total_eps*100:.1f}%" if total_eps > 0 else '0%'},
        {'Metric': 'YELLOW Count (4-5% Pullback)', 'Value': len(yellow_df)},
        {'Metric': 'PENDING (Awaiting D+1)', 'Value': len(pending_df)}
    ]
    summary_df = pd.DataFrame(summary_rows)

    with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
        res_df.to_excel(writer, sheet_name='All EP D+1 Performance', index=False)
        green_df.to_excel(writer, sheet_name='Green (Hold <= 4%)', index=False)
        red_df.to_excel(writer, sheet_name='Red (Fell > 5%)', index=False)
        summary_df.to_excel(writer, sheet_name='Summary Stats', index=False)

    print(f"\n✅ Saved Excel report: {excel_path}")

    # Dispatch to Telegram
    caption = (
        f"📊 *Episodic Pivot D+1 Performance Report (Last 50 Days)*\n\n"
        f"• Total EPs Evaluated: {total_eps}\n"
        f"🟢 *GREEN (Hold <=4% Pullback)*: {len(green_df)} ({len(green_df)/total_eps*100:.1f}%)\n"
        f"🔴 *RED (Fell > 5%)*: {len(red_df)} ({len(red_df)/total_eps*100:.1f}%)\n"
        f"🟡 *YELLOW (4-5% Pullback)*: {len(yellow_df)}\n"
        f"⏳ *PENDING (Awaiting D+1)*: {len(pending_df)}"
    )
    send_telegram_document(excel_path, caption=caption)

    return res_df

if __name__ == "__main__":
    run_ep_d1_performance_tracker()
