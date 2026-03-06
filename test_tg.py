import requests
import os
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("TELEGRAM_TOKEN")
chat_id = os.getenv("TELEGRAM_CHAT_ID")

def test_telegram():
    if not token or not chat_id:
        print("Telegram keys not found in .env")
        return
    
    msg = "🔍 StockGuru Connection Test: Is this working?"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": msg}
    
    try:
        r = requests.post(url, data=payload, timeout=10)
        print(f"Status: {r.status_code}")
        print(f"Response: {r.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    test_telegram()
