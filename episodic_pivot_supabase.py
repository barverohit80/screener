import pandas as pd
import os
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
import requests
from telegram_notifier import send_telegram_document

from dotenv import load_dotenv

load_dotenv()

# =====================================================================
# CONFIGURATION
# =====================================================================
DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING")
DAILY_SCREENER_DIR = os.getenv(
    "DAILY_SCREENER_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
)


def get_db_engine():
    if not DB_CONNECTION_STRING:
        print("❌ Error: DB_CONNECTION_STRING environment variable is not set.")
        return None
    try:
        return create_engine(DB_CONNECTION_STRING)
    except Exception as e:
        print(f"Error creating DB engine: {e}")
        return None

def send_telegram_with_excel(file_path, date_str, status_msg=None):
    """Orchestrates sending the EP Excel report to Telegram."""
    caption = f"📊 *Episodic Pivots (Last 30 Days)*\nTarget Date: {date_str}\n\nStocks showing strong volume and price momentum breakouts."
    
    if status_msg:
        caption = f"{status_msg}\n\n{caption}"
        
    return send_telegram_document(file_path, caption=caption)

def run_episodic_pivot_db_screener():
    engine = get_db_engine()
    if not engine:
        return

    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    is_weekend = now.weekday() >= 5

    cutoff_date = (now - timedelta(days=150)).strftime('%Y-%m-%d')
    print(f"Fetching bhavcopies data from the database (since {cutoff_date})...")
    try:
        query = f'SELECT * FROM bhavcopies WHERE "DATE" >= \'{cutoff_date}\''
        full_df = pd.read_sql(query, engine)
    except Exception as e:
        print(f"Error reading from database: {e}")
        return

    if full_df.empty:
        print("Error: Database is empty.")
        return

    # Standardize DATE column
    full_df['DATE'] = pd.to_datetime(full_df['DATE'])
    
    # Check for holiday/weekend context
    has_today_data = today_str in full_df['DATE'].dt.strftime('%Y-%m-%d').values
    status_msg = ""
    if is_weekend:
        status_msg = f"📅 Today is {now.strftime('%A')} ({today_str}).\n🛑 Weekend: Processing the latest available trading days from the database."
        print(status_msg)
    elif not has_today_data:
        status_msg = f"📅 Today is {now.strftime('%A')} ({today_str}).\n⚠️ Market Holiday or Data Missing: No data found for today. Processing historical data."
        print(status_msg)

    full_df = full_df.sort_values(['SYMBOL', 'DATE'])

    # Identify the target dates (Default to current date only, configurable via TARGET_DAYS_COUNT)
    all_dates = sorted(full_df['DATE'].unique())
    if len(all_dates) < 51:
        print(f"Error: Need at least 51 days of data for a 50-day average. Found {len(all_dates)}.")
        return
        
    target_days_count = int(os.getenv("TARGET_DAYS_COUNT", "1"))
    target_dates = all_dates[-target_days_count:]
    
    print(f"🚀 Running Episodic Pivot Scan for {len(target_dates)} target date(s): {[d.strftime('%Y-%m-%d') for d in target_dates]}...")

    # Load existing historical data to maintain delivery trend logic during backfill
    last_ep_deliv = {}
    try:
        # We load all existing data to initialize our trend tracker
        hist_df = pd.read_sql(f"SELECT * FROM \"episodicPivot\"", engine)
        if not hist_df.empty:
            hist_df['DATE'] = pd.to_datetime(hist_df['DATE'])
            hist_df['DELIV_QTY'] = pd.to_numeric(hist_df['DELIV_QTY'], errors='coerce')
    except Exception as e:
        hist_df = pd.DataFrame()
        print("Table 'episodicPivot' might not exist yet or error reading: " + str(e))

    total_hits_found = 0

    # Process each of the last 50 dates
    for target_date in target_dates:
        target_date_str = target_date.strftime('%Y-%m-%d')
        print(f"Analyzing {target_date_str}...", end=" ", flush=True)
        
        ep_results = []
        daily_hits = 0

        # Update our 'previous' delivery tracker based on data strictly before this target date
        if not hist_df.empty:
            past_data = hist_df[hist_df['DATE'] < target_date]
            if not past_data.empty:
                last_hits = past_data.sort_values('DATE').groupby('SYMBOL').tail(1)
                last_ep_deliv = dict(zip(last_hits['SYMBOL'], last_hits['DELIV_QTY']))

        # Analyze every symbol for this specific date
        for symbol, group in full_df.groupby('SYMBOL'):
            if target_date not in group['DATE'].values:
                continue
                
            group_list = group.reset_index(drop=True)
            loc = group_list[group_list['DATE'] == target_date].index[0]
            
            # Ensure we have at least 50 days of history PRIOR to this date
            if loc < 49: continue
            
            latest = group_list.iloc[loc]
            
            # New EP Requirements
            sma_vol_50 = group_list.iloc[loc-49 : loc+1]['VOLUME'].mean()
            min_avg_vol_ok = sma_vol_50 >= 100000
            vol_ratio = latest['VOLUME'] / sma_vol_50 if sma_vol_50 > 0 else 0
            vol_spike_ok = latest['VOLUME'] >= (sma_vol_50 * 3)
            range_day = latest['HIGH'] - latest['LOW']
            candle_strength_ok = latest['CLOSE'] >= (latest['LOW'] + (range_day * 0.60))
            price_ok = latest['CLOSE'] >= 50
            gap_up = latest['OPEN'] >= (latest['PREV'] * 1.05)
            gain_10 = latest['CLOSE'] >= (latest['PREV'] * 1.10)
            momentum_ok = gap_up or gain_10
            
            if min_avg_vol_ok and vol_spike_ok and candle_strength_ok and price_ok and momentum_ok:
                current_deliv = pd.to_numeric(latest['DELIV_QTY'], errors='coerce')
                trend = "NEW"
                if symbol in last_ep_deliv:
                    prev_deliv = pd.to_numeric(last_ep_deliv[symbol], errors='coerce')
                    if current_deliv > prev_deliv:
                        trend = "GREEN"
                    elif current_deliv < prev_deliv:
                        trend = "RED"
                    else:
                        trend = "SAME"
                
                res_row = latest.to_dict()
                res_row['DATE'] = target_date_str
                res_row['Weekday'] = target_date.strftime('%A')
                res_row['Vol_Ratio'] = round(vol_ratio, 2)
                res_row['Price_Change_%'] = round(((latest['CLOSE'] - latest['PREV']) / latest['PREV']) * 100, 2)
                res_row['SMA_Vol_50'] = round(sma_vol_50, 0)
                res_row['Deliv_Trend'] = trend
                
                ep_results.append(res_row)
                daily_hits += 1

        print(f"found {daily_hits} pivots.")
        total_hits_found += daily_hits

        # Save to 'episodicPivot' table for this specific date
        if ep_results:
            new_hits_df = pd.DataFrame(ep_results)
            
            # Deduplication: Delete existing records for this specific date before inserting
            try:
                with engine.begin() as conn:
                    conn.execute(text(f"DELETE FROM \"episodicPivot\" WHERE \"DATE\" = '{target_date_str}'"))
            except Exception:
                pass # Table might not exist yet
                
            try:
                new_hits_df.to_sql('episodicPivot', engine, if_exists='append', index=False)
                
                # Immediately update our running memory (hist_df) so the next day's loop sees these new inserts
                hist_df = pd.concat([hist_df, new_hits_df], ignore_index=True)
                hist_df['DATE'] = pd.to_datetime(hist_df['DATE']) # Ensure it stays datetime
            except Exception as e:
                print(f"Error inserting to DB on {target_date_str}: {e}")
        else:
             # Even if 0 results, delete old records for this date to maintain accuracy
             try:
                with engine.begin() as conn:
                    conn.execute(text(f"DELETE FROM \"episodicPivot\" WHERE \"DATE\" = '{target_date_str}'"))
             except Exception:
                pass

    print(f"\n===============================================================")
    print(f"SCAN COMPLETE: {total_hits_found} pivots found over {len(target_dates)} target date(s).")
    print(f"===============================================================\n")

    # Fetch last 40 days data for Telegram dispatch
    target_date = pd.to_datetime(target_dates[-1]) # Use the very last date for the report
    target_date_str = target_date.strftime('%Y-%m-%d')
    date_40_days_ago = (target_date - timedelta(days=40)).strftime('%Y-%m-%d')
    try:
        last_40_df = pd.read_sql(f"SELECT * FROM \"episodicPivot\" WHERE \"DATE\" >= '{date_40_days_ago}' ORDER BY \"DATE\" DESC", engine)
        if not last_40_df.empty:
            os.makedirs(DAILY_SCREENER_DIR, exist_ok=True)
            output_file = os.path.join(DAILY_SCREENER_DIR, "episodicPivot_last40days.xlsx")
            
            # Organize columns for better readability
            display_cols = ['SYMBOL', 'DATE', 'CLOSE', 'Price_Change_%', 'Vol_Ratio', 'Weekday', 'Deliv_Trend']
            available_cols = [c for c in display_cols if c in last_40_df.columns]
            last_40_df = last_40_df[available_cols + [c for c in last_40_df.columns if c not in available_cols]]
            
            # Simple Sorting: Group by SYMBOL alphabetically, then by DATE descending within group
            last_40_df = last_40_df.sort_values(by=['SYMBOL', 'DATE'], ascending=[True, False])
            
            # Format DATE as string to prevent '####' in Excel
            last_40_df['DATE'] = pd.to_datetime(last_40_df['DATE']).dt.strftime('%Y-%m-%d')
            
            # Split data into Today and Historical
            today_df = last_40_df[last_40_df['DATE'] == target_date_str]
            historical_df = last_40_df[last_40_df['DATE'] != target_date_str]
            
            # Write to Excel with multiple sheets
            with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                today_df.to_excel(writer, sheet_name=target_date_str, index=False)
                historical_df.to_excel(writer, sheet_name='Last 39 Days', index=False)
                
            print(f"✅ Saved data to {output_file} (Sheets: '{target_date_str}', 'Last 39 Days')")
            
            # Print latest hits nicely
            print("\n" + "="*95)
            title_str = "TODAY'S EPISODIC PIVOTS"
            print(f"{title_str:^95}")
            print("="*95)
            if not today_df.empty:
                print(today_df[available_cols].to_string(index=False))
            else:
                print("None found today.")
            print("="*95)
            
            # Send via Telegram
            send_telegram_with_excel(output_file, target_date_str, status_msg)
        else:
            print("No data found for the last 40 days in 'episodicPivot' table.")
    except Exception as e:
        print(f"Error fetching last 40 days data: {e}")

if __name__ == "__main__":
    run_episodic_pivot_db_screener()
