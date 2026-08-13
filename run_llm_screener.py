import pandas as pd
import os
from sqlalchemy import create_engine, text
import requests
import json
import time
from dotenv import load_dotenv
from telegram_notifier import send_telegram_message, send_telegram_document
from llm_analyzer import analyze_with_llm

load_dotenv()

# =====================================================================
# CONFIGURATION
# =====================================================================
DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DAILY_SCREENER_DIR = os.getenv(
    "DAILY_SCREENER_DIR",
    os.path.join(BASE_DIR, "output")
)


def get_db_engine():
    try:
        return create_engine(DB_CONNECTION_STRING)
    except Exception as e:
        print(f"Error creating DB engine: {e}")
        return None

def send_telegram_markdown(text, date_str):
    """Orchestrates sending AI analysis to Telegram, handling length limits."""
    header = f"🧠 *LLM Momentum Analysis ({date_str})*\n\n"
    full_message = header + text
    
    # Telegram limit is 4096 chars. If exceeded, send as document.
    if len(full_message) > 4000:
        print("⚠️ Message too long for a single post. Sending as document.")
        import tempfile
        temp_file = os.path.join(tempfile.gettempdir(), f"llm_analysis_{date_str}.md")
        with open(temp_file, "w") as f:
            f.write(full_message)
        return send_telegram_document(temp_file, caption=f"LLM Analysis for {date_str}")
    else:
        return send_telegram_message(full_message)

def analyze_with_gemini(prompt_text):
    """Bridge to the centralized llm_analyzer module."""
    return analyze_with_llm(prompt_text)

def prepare_llm_data():
    engine = get_db_engine()
    if not engine:
        return None, None

    print("Fetching episodic pivots from the database...")
    try:
        df = pd.read_sql("SELECT * FROM \"episodicPivot\"", engine)
    except Exception as e:
        print(f"Error reading from database: {e}")
        return None, None

    if df.empty:
        print("Error: Database table 'episodicPivot' is empty.")
        return None, None

    # Standardize DATE column
    df['DATE'] = pd.to_datetime(df['DATE'])
    
    # Identify the target date (Latest available in the DB)
    latest_date = df['DATE'].max()
    target_date_str = latest_date.strftime('%Y-%m-%d')
    
    print(f"Latest Pivot Date identified: {target_date_str}")
    
    # 1. Get ALL data to calculate Appearance_Count
    symbol_counts = df.groupby('SYMBOL').size().reset_index(name='Appearance_Count')
    
    # 2. Filter for only latest pivots
    today_df = df[df['DATE'] == latest_date].copy()
    
    if today_df.empty:
        print(f"⚠️ No Episodic Pivots found in the database for {target_date_str}.")
        return None, target_date_str
        
    # 3. Merge counts into today's df
    today_df = pd.merge(today_df, symbol_counts, on='SYMBOL', how='left')
    
    # 4. Format to match prompt expectations exactly
    today_df['DATE1'] = today_df['DATE'].dt.strftime('%d-%b-%Y')
    
    expected_cols = ['SYMBOL', 'DATE1', 'PREV', 'OPEN', 'HIGH', 'LOW', 
                     'LAST_PRICE', 'CLOSE', 'AVG_PRICE', 'VOLUME', 'TURNOVER_LACS', 
                     'NO_OF_TRADES', 'DELIV_QTY', 'DELIV_PER', 'DATE', 'Weekday', 
                     'Vol_Ratio', 'Price_Change_%', 'SMA_Vol_50', 'Appearance_Count']
                     
    for col in expected_cols:
        if col not in today_df.columns:
            today_df[col] = "NA"
            
    # Convert to CSV string format for LLM context
    csv_string = today_df[expected_cols].to_csv(index=True)
    return csv_string, target_date_str

def generate_llm_prompt(csv_data, date_str):
    prompt_file_path = os.getenv(
        "PROMPT_TEMPLATE_PATH",
        os.path.join(BASE_DIR, "Daily_momentom_screener.txt")
    )
    try:
        with open(prompt_file_path, "r") as f:
            prompt_text = f.read()
            
        combined_prompt = f"""
{prompt_text}

════════════════════════════════════════════════════════
INPUT DATA (CSV FORMAT) - DATE: {date_str}
════════════════════════════════════════════════════════
{csv_data}
"""
        return combined_prompt
    except Exception as e:
        print(f"Error reading prompt template: {e}")
        return None

if __name__ == "__main__":
    csv_data, date_str = prepare_llm_data()
    if csv_data:
        full_prompt = generate_llm_prompt(csv_data, date_str)
        if full_prompt:
            # 1. Save locally for reference
            os.makedirs(DAILY_SCREENER_DIR, exist_ok=True)
            prompt_save_path = os.path.join(DAILY_SCREENER_DIR, f"llm_prompt_{date_str}.txt")
            with open(prompt_save_path, "w") as f:
                f.write(full_prompt)
            print(f"Saved combined prompt to {prompt_save_path}")
            
            # 2. Analyze with Gemini
            analysis_result = analyze_with_gemini(full_prompt)
            
            if analysis_result:
                # 3. Save Analysis Result
                analysis_save_path = os.path.join(DAILY_SCREENER_DIR, f"EP_Output_{date_str}.md")
                with open(analysis_save_path, "w") as f:
                    f.write(analysis_result)
                print(f"Saved Gemini analysis to {analysis_save_path}")
                
                # 4. Send to Telegram
                send_telegram_markdown(analysis_result, date_str)
