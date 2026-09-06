import requests
import json
import time

# ============================
# بيانات الاتصال
# ============================

EMAIL = "yahia.x@outlook.sa"
API_KEY = "auIjjpVOvfy1KTix"
API_KEY_PASSWORD = "Yahia@1411"

# الوضع الحالي: DEMO أو REAL
current_mode = "DEMO"

def get_server():
    if current_mode == "DEMO":
        return "https://demo-api-capital.backend-capital.com"
    else:
        return "https://api-capital.backend-capital.backend-capital.com"

SERVER = get_server()

headers = {
    "X-CAP-API-KEY": API_KEY,
    "Content-Type": "application/json"
}

# ============================
# تسجيل الدخول
# ============================

def login():
    global SERVER
    SERVER = get_server()

    url = f"{SERVER}/api/v1/session"

    payload = {
        "identifier": EMAIL,
        "password": API_KEY_PASSWORD,
        "encryptedPassword": False
    }

    r = requests.post(url, headers=headers, data=json.dumps(payload))
    print("Login Response:", r.text)

    CST = r.headers.get("CST")
    XST = r.headers.get("X-SECURITY-TOKEN")

    return CST, XST

# ============================
# جلب الرصيد
# ============================

def get_balance(CST, XST):
    url = f"{SERVER}/api/v1/accounts"
    h = {"CST": CST, "X-SECURITY-TOKEN": XST}

    r = requests.get(url, headers=h)
    data = r.json()

    try:
        return data[0]["balance"]
    except:
        return 0

# ============================
# إغلاق جميع الصفقات حسب الاتجاه
# ============================

def close_positions(CST, XST, direction):
    url = f"{SERVER}/api/v1/positions"
    h = {"CST": CST, "X-SECURITY-TOKEN": XST}

    r = requests.get(url, headers=h)
    positions = r.json()

    if "positions" not in positions:
        return

    for pos in positions["positions"]:
        if pos["direction"] == direction:
            close_url = f"{SERVER}/api/v1/positions/close"
            close_data = {"positionId": pos["positionId"]}
            requests.post(close_url, headers=h, json=close_data)
            print("Closed:", pos["positionId"])

# ============================
# فتح صفقة برأس المال كامل × رافعة 100
# ============================

def open_full_position(CST, XST, direction):
    balance = get_balance(CST, XST)
    size = balance * 100   # رأس المال كامل × رافعة 100

    url = f"{SERVER}/api/v1/positions"
    h = {"CST": CST, "X-SECURITY-TOKEN": XST}

    data = {
        "direction": direction,
        "epic": "CS.D.EURUSD.MINI",
        "size": size
    }

    r = requests.post(url, headers=h, json=data)
    print("Open Position Response:", r.text)

# ============================
# Telegram Listener
# ============================

TOKEN = "8893700308:AAE5ahpKtEenHs_Q5kVGC6zDhfb832X66YI"
URL = f"https://api.telegram.org/bot{TOKEN}/getUpdates"

last_update_id = None
last_timestamp = None

def is_new_signal(timestamp):
    global last_timestamp
    if last_timestamp is None or timestamp > last_timestamp:
        last_timestamp = timestamp
        return True
    return False

def parse_json(text):
    try:
        data = json.loads(text)
        if data["action"] != "reverse":
            return None
        return data
    except:
        return None

# ============================
# التشغيل
# ============================

CST, XST = login()

while True:
    updates = requests.get(URL).json()

    if "result" in updates:
        for update in updates["result"]:
            if last_update_id is None or update["update_id"] > last_update_id:
                last_update_id = update["update_id"]

                msg = update.get("message", {})
                text = msg.get("text", "")

                # ============================
                # أوامر التبديل بين DEMO و REAL
                # ============================

                if text.strip() == "/demo":
                    current_mode = "DEMO"
                    CST, XST = login()
                    print("تم التحويل إلى الحساب التجريبي DEMO")
                    continue

                if text.strip() == "/real":
                    current_mode = "REAL"
                    CST, XST = login()
                    print("تم التحويل إلى الحساب الحقيقي REAL")
                    continue

                # ============================
                # تحليل رسائل التداول
                # ============================

                parsed = parse_json(text)
                if not parsed:
                    continue

                if not is_new_signal(parsed["timestamp"]):
                    continue

                signal = parsed["signal"]

                if signal == "BUY":
                    close_positions(CST, XST, "SELL")
                    open_full_position(CST, XST, "BUY")

                elif signal == "SELL":
                    close_positions(CST, XST, "BUY")
                    open_full_position(CST, XST, "SELL")

    time.sleep(1)
