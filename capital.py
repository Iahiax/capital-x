import requests
import json
from flask import Flask, request

# ===========================
# إعدادات عامة
# ===========================
EMAIL = "yahia.x@outlook.sa"
API_KEY = "ut2RpxSbx6fiDdHv"
API_KEY_PASSWORD = "Yahia@1411"

DEMO = True  # سيتم تغييره عبر بوت تيلجرام
SERVER = lambda: "https://demo-api-capital.backend-capital.com" if DEMO else "https://api-capital.backend-capital.com"

CST = None
XST = None

LEVERAGE = 100  # رافعة مالية 100:1

TELEGRAM_TOKEN = "8893700308:AAE5ahpKtEenHs_Q5kVGC6zDhfb832X66YI"
CHAT_ID = None  # سيتم ضبطه تلقائيًا عند أول رسالة

app = Flask(__name__)

# ===========================
# تسجيل الدخول
# ===========================
def login():
    global CST, XST
    url = f"{SERVER()}/api/v1/session"

    payload = {
        "identifier": EMAIL,
        "password": API_KEY_PASSWORD,
        "encryptedPassword": False
    }

    try:
        r = requests.post(url, headers={"X-CAP-API-KEY": API_KEY, "Content-Type": "application/json"}, data=json.dumps(payload))
        CST = r.headers.get("CST")
        XST = r.headers.get("X-SECURITY-TOKEN")
        print("✔️ جلسة جديدة:", CST, XST)
        return True
    except Exception as e:
        print("❌ فشل تسجيل الدخول:", e)
        return False

# ===========================
# إرسال رسالة تيلجرام
# ===========================
def tg(msg):
    global CHAT_ID
    if CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

# ===========================
# جلب الرصيد
# ===========================
def get_balance():
    url = f"{SERVER()}/api/v1/accounts"
    headers = {"CST": CST, "X-SECURITY-TOKEN": XST}
    r = requests.get(url, headers=headers)
    data = r.json()
    balance = float(data["accounts"][0]["balance"]["balance"])
    return balance

# ===========================
# إغلاق الصفقات حسب الاتجاه
# ===========================
def close_positions(direction):
    url = f"{SERVER()}/api/v1/positions"
    headers = {"CST": CST, "X-SECURITY-TOKEN": XST}

    try:
        r = requests.get(url, headers=headers)
        positions = r.json()

        if "positions" not in positions:
            return

        for pos in positions["positions"]:
            if pos["direction"] == direction:
                close_url = f"{SERVER()}/api/v1/positions/close"
                close_data = {"positionId": pos["positionId"]}
                requests.post(close_url, headers=headers, json=close_data)
                tg(f"🔒 تم إغلاق صفقة {direction} رقم {pos['positionId']}")
    except Exception as e:
        tg(f"⚠️ خطأ أثناء إغلاق الصفقات: {e}")

# ===========================
# تنفيذ أمر
# ===========================
def execute_order(action, symbol):
    global CST, XST

    # إعادة تسجيل الدخول إذا انتهت الجلسة
    if not CST or not XST:
        login()

    balance = get_balance()
    qty = balance * LEVERAGE  # التداول بكامل الرصيد × الرافعة

    # إغلاق الصفقة السابقة حسب الاتجاه
    if action == "buy":
        close_positions("SELL")
    elif action == "sell":
        close_positions("BUY")

    # فتح صفقة جديدة
    url = f"{SERVER()}/api/v1/positions"
    payload = {
        "symbol": symbol,
        "direction": "BUY" if action == "buy" else "SELL",
        "size": qty
    }

    try:
        r = requests.post(url, headers={"CST": CST, "X-SECURITY-TOKEN": XST}, json=payload)
        tg(f"✔️ تم تنفيذ أمر {action} على {symbol} بحجم {qty}")
        return True
    except Exception as e:
        tg(f"❌ فشل تنفيذ الأمر: {e}")
        login()
        return False

# ===========================
# استقبال Webhook من TradingView
# ===========================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    action = data.get("action")
    symbol = data.get("symbol")

    if action in ["buy", "sell"]:
        execute_order(action, symbol)
        return {"status": "ok"}
    else:
        return {"status": "invalid"}

# ===========================
# بوت تيلجرام للتحكم
# ===========================
@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_bot():
    global DEMO, CHAT_ID

    data = request.get_json()
    CHAT_ID = data["message"]["chat"]["id"]
    text = data["message"]["text"]

    if text == "/demo":
        DEMO = True
        login()
        tg("🔄 تم التحويل إلى حساب Demo")

    elif text == "/real":
        DEMO = False
        login()
        tg("🔄 تم التحويل إلى حساب Real")

    elif text == "/balance":
        tg(f"💰 الرصيد الحالي: {get_balance()}")

    elif text == "/session":
        tg(f"CST: {CST}\nXST: {XST}")

    elif text == "/start":
        tg("🤖 بوت التداول جاهز.\nالأوامر:\n/demo\n/real\n/balance\n/session")

    return {"ok": True}

# ===========================
# تشغيل السيرفر
# ===========================
if __name__ == "__main__":
    login()
    app.run(host="0.0.0.0", port=8000)
