import os
from dotenv import load_dotenv

load_dotenv()

# Konfigurasi Umum / Non-Sensitif
DATA_FILE = os.getenv("DATA_FILE", "financial_data.json")
API_HOST = os.getenv("KLEDO_BASE_HOST", "http://rotibakarwisuda.api.kledo.com/api/v1")
X_APP = os.getenv("X_APP", "finance")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")

# Konfigurasi Kredensial (Dibaca langsung dari Environment Variable / .env)
EMAIL = os.getenv("KLEDO_EMAIL")
PASSWORD = os.getenv("KLEDO_PASSWORD")
KLEDO_COOKIE_NAME = os.getenv("KLEDO_COOKIE_NAME")
KLEDO_COOKIE_VALUE = os.getenv("KLEDO_TOKEN") or os.getenv("KLEDO_COOKIE_VALUE")