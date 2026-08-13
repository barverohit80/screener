import requests
from datetime import datetime
import os

def check_nse_report():
    # Get current system date
    now = datetime.now()
    date_str = now.strftime("%d%m%Y")
    day_name = now.strftime("%A")
    base_dir = os.getenv("DAILY_SCREENER_DIR", os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(base_dir, exist_ok=True)
    filename = os.path.join(base_dir, f"nse_52wk_{date_str}.csv")
    
    # 1. Check for Weekends
    if now.weekday() >= 5: # 5 = Saturday, 6 = Sunday
        print(f"📅 Today is {day_name} ({now.strftime('%d-%b-%Y')}).")
        print("🛑 Result: It is a Weekend. NSE does not generate reports on Saturdays or Sundays.")
        return

    # 2. Setup NSE Session (Required for security)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.nseindia.com/"
    }
    
    session = requests.Session()
    
    try:
        print(f"Connecting to NSE for today's report ({now.strftime('%d-%b-%Y')})...")
        # Initialize session cookies
        session.get("https://www.nseindia.com/", headers=headers, timeout=10)
        
        # 3. Attempt to download from Archive
        url = f"https://nsearchives.nseindia.com/content/CM_52_wk_High_low_{date_str}.csv"
        response = session.get(url, headers=headers)
        
        if response.status_code == 200:
            with open(filename, "wb") as f:
                f.write(response.content)
            print(f"✅ Success! Today's file downloaded: {filename}")
            
        elif response.status_code == 404:
            print(f"📅 Date: {now.strftime('%d-%b-%Y')} ({day_name})")
            print("❌ Result: File Not Found.")
            print("-" * 30)
            print("Possible Reasons:")
            print("1. Trading Holiday: If today is a national holiday, no file is generated.")
            print("2. Timing: Today's report is usually uploaded AFTER 6:30 PM IST.")
            print("3. Market in Progress: If markets are still open, the final report isn't ready.")
            print("-" * 30)
            
        else:
            print(f"⚠️ Unexpected Status Code: {response.status_code}")
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    check_nse_report()
