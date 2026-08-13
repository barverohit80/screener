import pandas as pd
import os
from datetime import datetime, timedelta
import glob
from sqlalchemy import create_engine, text

# Import functions from existing scripts
from download_bhavcopy_to_supabase import download_bhavcopies_to_db
from episodic_pivot_supabase import run_episodic_pivot_db_screener, get_db_engine
from download_nse_52wk import check_nse_report
from run_llm_screener import analyze_with_gemini, send_telegram_markdown
from ep_d1_performance_tracker import run_ep_d1_performance_tracker

# =====================================================================
# CONFIGURATION
# =====================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DAILY_SCREENER_DIR = os.getenv("DAILY_SCREENER_DIR", os.path.join(BASE_DIR, "output"))
PROMPT_TEMPLATE_PATH = os.getenv("PROMPT_TEMPLATE_PATH", os.path.join(BASE_DIR, "Daily_momentom_screener.txt"))

def get_latest_52wk_file():
    """Finds the most recent 52-week high/low file."""
    os.makedirs(DAILY_SCREENER_DIR, exist_ok=True)
    patterns = [
        os.path.join(DAILY_SCREENER_DIR, "CM_52_wk_High_low_*.csv"),
        os.path.join(DAILY_SCREENER_DIR, "nse_52wk_*.csv"),
        os.path.join(BASE_DIR, "CM_52_wk_High_low_*.csv"),
        os.path.join(BASE_DIR, "nse_52wk_*.csv"),
        os.path.join(os.getcwd(), "CM_52_wk_High_low_*.csv"),
        os.path.join(os.getcwd(), "nse_52wk_*.csv"),
    ]
    
    all_files = []
    for pattern in patterns:
        all_files.extend(glob.glob(pattern))
        
    if not all_files:
        return None
    
    # Sort by modification time
    return max(all_files, key=os.path.getmtime)

def prepare_master_llm_data(target_date_str):
    engine = get_db_engine()
    if not engine:
        return None

    print(f"Fetching episodic pivots for {target_date_str}...")
    try:
        # Get all data for Appearance_Count
        full_df = pd.read_sql("SELECT * FROM \"episodicPivot\"", engine)
        if full_df.empty:
            print("Error: 'episodicPivot' table is empty.")
            return None
            
        full_df['DATE'] = pd.to_datetime(full_df['DATE'])
        symbol_counts = full_df.groupby('SYMBOL').size().reset_index(name='Appearance_Count')
        
        # Filter for target date
        target_date = pd.to_datetime(target_date_str)
        today_df = full_df[full_df['DATE'] == target_date].copy()
        
        if today_df.empty:
            print(f"⚠️ No pivots found for {target_date_str}")
            return None
            
        # Merge appearance counts
        today_df = pd.merge(today_df, symbol_counts, on='SYMBOL', how='left')
        
        # 52-Week High Merge
        latest_52wk_path = get_latest_52wk_file()
        if latest_52wk_path:
            print(f"Merging 52-week high data from {os.path.basename(latest_52wk_path)}...")
            try:
                df_52wk = pd.read_csv(latest_52wk_path, skiprows=2)
                df_52wk.columns = [c.strip().replace('"', '') for c in df_52wk.columns]
                df_52wk['SYMBOL'] = df_52wk['SYMBOL'].str.strip()
                
                # Merge 'Adjusted_52_Week_High' -> '52W_High'
                today_df = pd.merge(today_df, df_52wk[['SYMBOL', 'Adjusted_52_Week_High']], on='SYMBOL', how='left')
                today_df = today_df.rename(columns={'Adjusted_52_Week_High': '52W_High'})
            except Exception as e:
                print(f"⚠️ Failed to merge 52-week high data: {e}")
        else:
            print("⚠️ No 52-week high file found. Proceeding without it.")

        # Formatting for LLM Prompt
        today_df['DATE1'] = today_df['DATE'].dt.strftime('%d-%b-%Y')
        
        expected_cols = ['SYMBOL', 'DATE1', 'PREV', 'OPEN', 'HIGH', 'LOW', 
                         'LAST_PRICE', 'CLOSE', 'AVG_PRICE', 'VOLUME', 'TURNOVER_LACS', 
                         'NO_OF_TRADES', 'DELIV_QTY', 'DELIV_PER', 'DATE', 'Weekday', 
                         'Vol_Ratio', 'Price_Change_%', 'SMA_Vol_50', 'Appearance_Count', '52W_High']
                         
        for col in expected_cols:
            if col not in today_df.columns:
                today_df[col] = "NA"
                
        return today_df[expected_cols].to_csv(index=True)
    except Exception as e:
        print(f"Error preparing LLM data: {e}")
        return None

def run_pipeline():
    print("\n" + "═"*60)
    print("      EPISODIC PIVOT MASTER PIPELINE ORCHESTRATOR      ")
    print("═"*60 + "\n")

    # 1. Sync Bhavcopy
    lookback_days = int(os.getenv("LOOKBACK_DAYS", "3"))
    print(f"STEP 1: Syncing Bhavcopy to Supabase (Lookback: {lookback_days} days)...")
    download_bhavcopies_to_db(lookback_days)
    
    # 2. Sync 52-Week High Data
    print("\nSTEP 2: Syncing 52-Week High Data...")
    check_nse_report() # Note: This script downloads to current dir, usually workspace/screener
    # We should move it to dailyScreener if it's not there, but check_nse_report is hardcoded to current dir
    
    # 3. Run EP Screener
    print("\nSTEP 3: Running Episodic Pivot Scan...")
    run_episodic_pivot_db_screener()
    
    # 4. Identify the target date for LLM (Latest date in pivots)
    engine = get_db_engine()
    with engine.connect() as conn:
        result = conn.execute(text("SELECT MAX(\"DATE\") FROM \"episodicPivot\""))
        latest_date = result.scalar()
    
    if not latest_date:
        print("❌ No pivots found. Pipeline stopped.")
        return

    if isinstance(latest_date, str):
        target_date_str = latest_date
    else:
        target_date_str = latest_date.strftime('%Y-%m-%d')
        
    print(f"\nSTEP 4: Preparing LLM Prompt for {target_date_str}...")
    
    csv_data = prepare_master_llm_data(target_date_str)
    
    if csv_data:
        with open(PROMPT_TEMPLATE_PATH, "r") as f:
            prompt_text = f.read()
            
        combined_prompt = f"""
{prompt_text}

════════════════════════════════════════════════════════
INPUT DATA (CSV FORMAT) - DATE: {target_date_str}
════════════════════════════════════════════════════════
{csv_data}
"""
        output_path = os.path.join(DAILY_SCREENER_DIR, f"llm_prompt_{target_date_str}.txt")
        with open(output_path, "w") as f:
            f.write(combined_prompt)
            
        print(f"Generated combined prompt at: {output_path}")

        # 5. Run Gemini Analysis
        print("\nSTEP 5: Running AI Analysis with Gemini...")
        analysis_result = analyze_with_gemini(combined_prompt)
        
        if analysis_result:
            # Save Analysis Result
            analysis_save_path = os.path.join(DAILY_SCREENER_DIR, f"EP_Output_{target_date_str}.md")
            with open(analysis_save_path, "w") as f:
                f.write(analysis_result)
            print(f"✅ AI Analysis complete! Report saved at: {analysis_save_path}")
            
            # Send to Telegram
            send_telegram_markdown(analysis_result, target_date_str)
        else:
            print("⚠️ AI Analysis skipped or failed.")

        # 6. Run D+1 Performance Tracking
        print("\nSTEP 6: Running D+1 Performance Tracking (Last 50 Days)...")
        run_ep_d1_performance_tracker()

        print("\n" + "═"*60 + "\n")
    else:
        print("❌ Pipeline failed during LLM data preparation.")

if __name__ == "__main__":
    run_pipeline()
