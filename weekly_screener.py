import pandas as pd
import os
from datetime import datetime
from sqlalchemy import create_engine
import requests
from dotenv import load_dotenv

load_dotenv()

# =====================================================================
# CONFIGURATION
# =====================================================================
DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DAILY_SCREENER_DIR = os.getenv(
    "DAILY_SCREENER_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
)


def get_db_engine():
    try:
        return create_engine(DB_CONNECTION_STRING)
    except Exception as e:
        print(f"Error creating DB engine: {e}")
        return None

def send_telegram_with_excel(file_path, date_str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials not configured. Skipping dispatch.")
        return
        
    print("Preparing to send Excel file to Telegram...")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    caption = f"📊 *Weekly Momentum Screener Results*\nDate: {date_str}\n\nHigh conviction stocks with price and delivery volume momentum."
    
    try:
        with open(file_path, 'rb') as f:
            files = {'document': (os.path.basename(file_path), f)}
            data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption, 'parse_mode': 'Markdown'}
            response = requests.post(url, data=data, files=files)
            
            if response.status_code == 200:
                print("✅ Excel report sent to Telegram successfully!")
            else:
                print(f"❌ Failed to send to Telegram: {response.text}")
    except Exception as e:
        print(f"❌ Failed to send Telegram message: {e}")

def weekly_momentum_screener():
    os.makedirs(DAILY_SCREENER_DIR, exist_ok=True)
    output_file = os.path.join(DAILY_SCREENER_DIR, "weekly_momentum_results.xlsx")
    
    print(f"🚀 Running Weekly Momentum Scan from Supabase Database...")
    print(f"Criteria: Price > 100, Deliv Vol (Today, T-7, T-14) > 100k, Price(Today) > Price(T-7) > Price(T-14)")
    
    engine = get_db_engine()
    if not engine:
        return

    cutoff_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
    print(f"Fetching recent data from the database (since {cutoff_date})...")
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
    full_df = full_df.sort_values(['SYMBOL', 'DATE'])
    
    # 2. Identify the target date (Latest available)
    all_dates = sorted(full_df['DATE'].unique())
    if len(all_dates) < 15:
        print(f"Error: Need at least 15 days of data for -14 day comparison. Found {len(all_dates)}.")
        return
        
    target_date = pd.to_datetime(all_dates[-1])
    target_date_str = target_date.strftime('%Y-%m-%d')
    
    results = []

    # 3. Analyze every symbol
    for symbol, group in full_df.groupby('SYMBOL'):
        # Standardize types
        group['CLOSE'] = pd.to_numeric(group['CLOSE'], errors='coerce')
        group['DELIV_QTY'] = pd.to_numeric(group['DELIV_QTY'], errors='coerce')
        
        # Sort group by date
        group = group.sort_values('DATE').reset_index(drop=True)
        
        # Ensure the symbol is present on the target date
        if target_date not in group['DATE'].values:
            continue
            
        latest = group[group['DATE'] == target_date].iloc[0]
        
        # --- CALENDAR OFFSET LOGIC (with holiday fallback) ---
        date_t7_target = target_date - pd.Timedelta(days=7)
        date_t14_target = target_date - pd.Timedelta(days=14)
        
        # Find the latest available trading day on or before the target offsets
        history_t7 = group[group['DATE'] <= date_t7_target]
        history_t14 = group[group['DATE'] <= date_t14_target]
        
        if history_t7.empty or history_t14.empty:
            continue
            
        t_minus_7 = history_t7.iloc[-1]
        t_minus_14 = history_t14.iloc[-1]
        
        # Actual dates found
        actual_date_t7 = t_minus_7['DATE'].strftime('%Y-%m-%d')
        actual_date_t14 = t_minus_14['DATE'].strftime('%Y-%m-%d')
        
        # --- FILTERS ---
        # 1. Price > 100
        price_ok = latest['CLOSE'] > 100
        
        # 2. Delivery Volume > 100,000 for all three points
        deliv_ok = (latest['DELIV_QTY'] > 100000) and (t_minus_7['DELIV_QTY'] > 100000) and (t_minus_14['DELIV_QTY'] > 100000)
        
        # 3. Price(Today) > Price(T-7) AND Price(T-7) > Price(T-14)
        momentum_ok = (latest['CLOSE'] > t_minus_7['CLOSE']) and (t_minus_7['CLOSE'] > t_minus_14['CLOSE'])
        
        if price_ok and deliv_ok and momentum_ok:
            results.append({
                'SYMBOL': symbol,
                'Date': target_date_str,
                'Price_Today': round(latest['CLOSE'], 2),
                'Date_T7': actual_date_t7,
                'Price_T7': round(t_minus_7['CLOSE'], 2),
                'Date_T14': actual_date_t14,
                'Price_T14': round(t_minus_14['CLOSE'], 2),
                'current_day_del_vol': int(latest['DELIV_QTY']),
                't-7_del_vol': int(t_minus_7['DELIV_QTY']),
                't-14_del_vol': int(t_minus_14['DELIV_QTY']),
                'Weekly_Gain_%': round(((latest['CLOSE'] - t_minus_7['CLOSE']) / t_minus_7['CLOSE']) * 100, 2),
                'BiWeekly_Gain_%': round(((latest['CLOSE'] - t_minus_14['CLOSE']) / t_minus_14['CLOSE']) * 100, 2)
            })

    # 4. Display and Save
    if results:
        res_df = pd.DataFrame(results).sort_values('Weekly_Gain_%', ascending=False)
        
        # Save to Excel (.xlsx) instead of CSV
        res_df.to_excel(output_file, index=False)
        
        print("\n" + "="*145)
        print(f"{'WEEKLY MOMENTUM STOCKS IDENTIFIED (WITH DELIVERY VOLUME)':^145}")
        print("="*145)
        # Expanded display columns
        display_cols = [
            'SYMBOL', 'Price_Today', 'Price_T7', 'Price_T14', 
            'current_day_del_vol', 't-7_del_vol', 't-14_del_vol', 'Weekly_Gain_%'
        ]
        print(res_df[display_cols].to_string(index=False))
        print("="*145)
        print(f"✅ Success: {len(results)} stocks found and saved to {output_file}")
        
        # Trigger Telegram Dispatch
        send_telegram_with_excel(output_file, target_date_str)
    else:
        print(f"\nNo stocks met the criteria on {target_date_str}.")

if __name__ == "__main__":
    weekly_momentum_screener()
