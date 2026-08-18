import os
import logging
from dotenv import load_dotenv

# Muat variabel environment dari file .env
load_dotenv()

# Konfigurasi Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Kredensial dan API
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
API_HOST = os.getenv("KLEDO_BASE_HOST", "http://rotibakarwisuda.api.kledo.com/api/v1")
X_APP = os.getenv("X_APP", "finance")
EMAIL = os.getenv("KLEDO_EMAIL")
PASSWORD = os.getenv("KLEDO_PASSWORD")

DATA_FILE = "data.json"