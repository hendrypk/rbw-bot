import os
from dotenv import load_dotenv

load_dotenv()

# Konfigurasi API & Kredensial
API_HOST = os.getenv("KLEDO_BASE_HOST", "http://rotibakarwisuda.api.kledo.com/api/v1")
X_APP = os.getenv("X_APP", "finance")
EMAIL = os.getenv("KLEDO_EMAIL", "rotibakar.wisuda@gmail.com")
PASSWORD = os.getenv("KLEDO_PASSWORD", "Wisuda2027@")

# Konfigurasi Cookie (Menggunakan KLEDO_TOKEN atau KLEDO_COOKIE_VALUE)
KLEDO_COOKIE_NAME = os.getenv("KLEDO_COOKIE_NAME", "kledo_pat_001Bsw_AAnaKgeYODgirD917D57TyNbrIHKuHDPy2dv0hIUtlqKelQI4scfUQ01RihlGcrWWHFRK0ILryIdNUwd")
# Mengambil dari KLEDO_TOKEN jika KLEDO_COOKIE_VALUE masih bernilai default/kosong
KLEDO_COOKIE_VALUE = os.getenv("KLEDO_COOKIE_VALUE") if os.getenv("KLEDO_COOKIE_VALUE") != "ISI_NILAI_TOKEN_ANDA_DISINI" else os.getenv("KLEDO_TOKEN")

# Telegram (jika dibutuhkan di file lain)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")