import json
import requests

API_HOST = 'http://rotibakarwisuda.api.kledo.com/api/v1'
EMAIL = "rotibakar.wisuda@gmail.com"
PASSWORD = "Wisuda2027@"

login_url = f"{API_HOST}/authentication/singleLogin"

# Payload lengkap sesuai Postman
payload = {
    "email": EMAIL,
    "password": PASSWORD,
    "remember_me": 1,
    "is_otp": 0,
    "use_jwt": 0,
    "include_init": 1,
    "apple_identity_token": None
}

headers = {
    'Content-Type': 'application/json',
    'Accept': '*/*',
    'app-client': 'web',
    'X-App': 'finance'
}

# Masukkan cookie token di sini (sesuaikan nama cookie dan nilainya dari Postman)
cookies = {
    "kledo_pat_001Bsw_AAnaKgeYODgirD917D57TyNbrIHKuHDPy2dv0hIUtlqKelQI4scfUQ01RihlGcrWWHFRK0ILryIdNUwd": "ISI_NILAI_TOKEN_ANDA_DISINI"
}

# Atau jika ingin menggunakan format string header Cookie langsung:
# headers['Cookie'] = "nama_cookie=nilai_token"

session = requests.Session()

try:
    print("Mengirim request login ke Kledo dengan cookie token...")
    response = session.post(login_url, json=payload, headers=headers, cookies=cookies)
    
    res_data = response.json()
    response.raise_for_status()
    
    print("🎉 LOGIN BERHASIL!")
    print(json.dumps(res_data, indent=2, ensure_ascii=False))
    
    # Menampilkan cookies yang aktif/diterima kembali
    if session.cookies:
        print("\n🍪 Cookies Aktif:")
        for cookie in session.cookies:
            print(f"  {cookie.name} = {cookie.value}")
            
except requests.exceptions.HTTPError as e:
    print(f"❌ HTTP Error {response.status_code}:")
    try:
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    except Exception:
        print(response.text)
except Exception as e:
    print(f"❌ Error Lain: {e}")