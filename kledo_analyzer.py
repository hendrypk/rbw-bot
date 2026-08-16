from collections import Counter
from datetime import datetime
import json
import os
from dotenv import load_dotenv
import requests

# Muat variabel environment dari file .env
load_dotenv()

# Ambil data sensitif dan konfigurasi dari environment variables
API_HOST = os.getenv(
    "KLEDO_BASE_HOST", "http://rotibakarwisuda.api.kledo.com/api/v1"
)
X_APP = os.getenv("X_APP", "finance")
EMAIL = os.getenv("KLEDO_EMAIL")
PASSWORD = os.getenv("KLEDO_PASSWORD")


def create_logged_in_session():
  """Melakukan login otomatis menggunakan requests.Session() dengan payload

  dan header yang mengambil data dari environment variables.
  """
  if not EMAIL or not PASSWORD:
    print(
        "❌ Error: KLEDO_EMAIL atau KLEDO_PASSWORD belum diatur di dalam file"
        " .env!"
    )
    return None

  session = requests.Session()
  login_url = f"{API_HOST}/authentication/singleLogin"

  payload = {
      "email": EMAIL,
      "password": PASSWORD,
      "remember_me": 1,
      "is_otp": 0,
      "use_jwt": 0,
      "include_init": 1,
      "apple_identity_token": None,
  }

  headers = {
      "Content-Type": "application/json",
      "Accept": "*/*",
      "app-client": "web",
      "X-App": X_APP,
  }

  print("🔐 Sedang melakukan autentikasi ke Kledo...")
  try:
    response = session.post(login_url, json=payload, headers=headers)
    response.raise_for_status()

    print("🎉 Berhasil login dan sesi aktif terbentuk!")
    return session
  except Exception as e:
    print(f"❌ Gagal login: {e}")
    if "response" in locals():
      print(response.text)
    return None


def fetch_and_analyze():
  # 1. Dapatkan Session Aktif via Login
  session = create_logged_in_session()
  if not session:
    print("❌ Autentikasi gagal. Periksa kembali pengaturan file .env Anda.")
    return

  # 2. Ambil Data Invoice menggunakan Session yang membawa Cookie/Token
  url = f"{API_HOST}/finance/invoices?date_from=2026-08-01&date_to=2026-08-17&per_page=100"

  headers = {"Accept": "application/json", "X-App": X_APP}

  print("📡 Menarik data invoice dari Kledo...")
  try:
    response = session.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()

    res_content = data.get("data", {})
    invoices = (
        res_content.get("data", [])
        if isinstance(res_content, dict)
        else res_content
    )

    if not invoices:
      print("⚠️ Data invoice tidak ditemukan dalam rentang tanggal tersebut.")
      return

    print(f"🎉 Berhasil menarik {len(invoices)} invoice.")

    # --- 3. ANALISIS JAM RAMAI (PEAK HOURS) ---
    hour_list = []
    for inv in invoices:
      created_at = (
          inv.get("created_at")
          or inv.get("log", {}).get("action", {}).get("created_at")
          or inv.get("trans_date")
      )

      if created_at:
        try:
          if " " in created_at:
            dt_str = created_at[:19]
            fmt = (
                "%Y-%m-%d %H:%M:%S" if len(dt_str) == 19 else "%Y-%m-%d %H:%M"
            )
            dt = datetime.strptime(dt_str, fmt)
            hour_list.append(dt.hour)
        except ValueError:
          continue

    peak_hours = Counter(hour_list).most_common()

    print("\n--- 📊 ANALISIS JAM RAMAI (PEAK HOURS) ---")
    print(f"{'Jam':<10} | {'Jumlah Transaksi':<15}")
    print("-" * 30)
    if peak_hours:
      for hour, count in sorted(peak_hours):
        print(f"{hour:02d}:00    | {count}")
    else:
      print("⚠️ Belum ada data jam transaksi spesifik yang valid.")

    # Simpan cache lokal
    with open("kledo_data_cache.json", "w", encoding="utf-8") as f:
      json.dump(invoices, f, indent=4, ensure_ascii=False)
    print("\n💾 Data mentah berhasil disimpan ke 'kledo_data_cache.json'")

  except Exception as e:
    print(f"❌ Terjadi kesalahan saat menarik data: {e}")


if __name__ == "__main__":
  fetch_and_analyze()