import os
import requests
import time
import json
from dotenv import load_dotenv

load_dotenv()

# =====================================================================
# TELEGRAM CONFIGURATION
# =====================================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(text, parse_mode='Markdown'):
    """Sends a text message to Telegram with retry logic."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials not configured.")
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': parse_mode
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"Sending Telegram message (Attempt {attempt+1}/{max_retries})...")
            response = requests.post(url, data=payload, timeout=60)
            if response.status_code == 200:
                print("✅ Telegram message sent successfully!")
                return True
            else:
                print(f"⚠️ Attempt {attempt+1} failed: {response.text}")
        except Exception as e:
            print(f"⚠️ Attempt {attempt+1} connection error: {e}")
        
        if attempt < max_retries - 1:
            wait_time = (attempt + 1) * 10
            print(f"Retrying in {wait_time}s...")
            time.sleep(wait_time)
            
    print("❌ Failed to send Telegram message after multiple attempts.")
    return False

def send_telegram_document(file_path, caption="", parse_mode='Markdown'):
    """Sends a document to Telegram with retry logic."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials not configured.")
        return False
        
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'caption': caption,
        'parse_mode': parse_mode
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"Sending Telegram document: {os.path.basename(file_path)} (Attempt {attempt+1}/{max_retries})...")
            with open(file_path, 'rb') as f:
                files = {'document': (os.path.basename(file_path), f)}
                response = requests.post(url, data=payload, files=files, timeout=60)
            
            if response.status_code == 200:
                print("✅ Telegram document sent successfully!")
                return True
            else:
                print(f"⚠️ Attempt {attempt+1} failed: {response.text}")
        except Exception as e:
            print(f"⚠️ Attempt {attempt+1} connection error: {e}")
        
        if attempt < max_retries - 1:
            wait_time = (attempt + 1) * 10
            print(f"Retrying in {wait_time}s...")
            time.sleep(wait_time)
            
    print("❌ Failed to send Telegram document after multiple attempts.")
    return False

if __name__ == "__main__":
    # Connectivity Test
    print("🚀 Running Telegram Connectivity Test...")
    test_msg = "🔔 *Telegram Connectivity Test*\nThis is a test message from the isolated notifier script."
    success = send_telegram_message(test_msg)
    
    if success:
        print("\nTesting document upload with a sample file...")
        import tempfile
        test_file = os.path.join(tempfile.gettempdir(), "test_telegram.txt")
        with open(test_file, "w") as f:
            f.write("This is a test file for Telegram upload.")
        
        send_telegram_document(test_file, caption="Sample Document Test")
    else:
        print("\n❌ Initial message test failed. Please check network/credentials.")
