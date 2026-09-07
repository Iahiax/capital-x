import requests
import json
from flask import Flask, request

# ===========================
# إعدادات عامة
# ===========================
EMAIL = "yahia.x@outlook.sa"
API_KEY = "ut2RpxSbx6fiDdHv"
API_KEY_PASSWORD = "Yahia@1411"

DEMO = True  # يتم التبديل عبر أوامر تيلجرام
LEVERAGE = 100  # رافعة مالية 100:1

TELEGRAM_TOKEN = "8893700308:AAE5ahpKtEenHs_Q5kVGC6zDhfb832X66YI"
CHAT_ID = None  # يتم ضبطه تلقائيًا عند أول رسالة (قناة أو خاص)

CST = None
XST = None

app = Flask(__name__)

def SERVER():
    return "https://demo-api-capital.backend-capital.com" if DEMO else "https://api-capital.backend-capital.com"

def base_headers():
    return {
        "X-CAP-API-KEY": API_KEY,
        "Content-Type": "application/json"
    }

def auth_headers():
    h = base_headers()
    if CST:
        h["CST"] = CST
    if XST:
        h["X-SECURITY-TOKEN"] = XST
    return h

# ===========================
# تسجيل الدخول + إعادة تسجيل تلقائيًا
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
        r = requests.post(url, headers=base_headers(), data=json.dumps(payload))
        CST = r.headers.get("CST")
        XST = r.headers.get("X-SECURITY-TOKEN")
        print("✔️ جلسة جديدة:", CST, XST)
        tg("🔑 تم إنشاء جلسة جديدة مع Capital.com")
        return True
    except Exception as e:
        print("❌ فشل تسجيل الدخول:", e)
        tg(f"❌ فشل تسجيل الدخول: {e}")
        return False

def ensure_session():
    if not CST or not XST:
        login()

# ===========================
# إرسال رسالة تيلجرام
# ===========================
def tg(msg):
    global CHAT_ID
    if not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg})
    except Exception as e:
        print("Telegram send error:", e)

# ===========================
# جلب الرصيد
# ===========================
def get_balance():
    ensure_session()
    url = f"{SERVER()}/api/v1/accounts"
    try:
        r = requests.get(url, headers=auth_headers())
        data = r.json()

        # دعم أكثر من شكل للـ JSON
        if isinstance(data, list):
            balance = float(data[0]["balance"])
        elif "accounts" in data:
            balance = float(data["accounts"][0]["balance"]["balance"])
        else:
            raise Exception("Unknown accounts format")

        return balance
    except Exception as e:
        tg(f"⚠️ خطأ أثناء جلب الرصيد: {e}")
        return 0.0

# ===========================
# إغلاق الصفقات حسب الاتجاه
# ===========================
def close_positions(direction):
    ensure_session()
    url = f"{SERVER()}/api/v1/positions"

    try:
        r = requests.get(url, headers=auth_headers())
        positions = r.json()

        if "positions" not in positions:
            return

        for pos in positions["positions"]:
            if pos["direction"] == direction:
                close_url = f"{SERVER()}/api/v1/positions/close"
                close_data = {"positionId": pos["positionId"]}
                requests.post(close_url, headers=auth_headers(), json=close_data)
                tg(f"🔒 تم إغلاق صفقة {direction} رقم {pos['positionId']}")
    except Exception as e:
        tg(f"⚠️ خطأ أثناء إغلاق الصفقات: {e}")

# ===========================
# تنفيذ أمر (BUY / SELL) بكامل الرصيد × الرافعة
# ===========================
def execute_order(action, epic):
    ensure_session()

    balance = get_balance()
    qty = balance * LEVERAGE  # التداول بكامل الرصيد × الرافعة

    # إغلاق الصفقات السابقة حسب الاتجاه
    if action == "buy":
        close_positions("SELL")
    elif action == "sell":
        close_positions("BUY")

    # فتح صفقة جديدة
    url = f"{SERVER()}/api/v1/positions"
    payload = {
        "epic": epic,                      # Capital.com تستخدم epic وليس symbol
        "direction": "BUY" if action == "buy" else "SELL",
        "size": qty
    }

    try:
        r = requests.post(url, headers=auth_headers(), json=payload)
        tg(f"✔️ تم تنفيذ أمر {action.upper()} على {epic} بحجم {qty}")
        print("Order response:", r.text)
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
    data = request.get_json() or {}
    action = data.get("action")   # "buy" أو "sell"
    epic = data.get("epic")       # مثال: "CS.D.EURUSD.MINI"

    if action in ["buy", "sell"] and epic:
        execute_order(action, epic)
        return {"status": "ok"}
    else:
        return {"status": "invalid"}, 400

# ===========================
# بوت تيلجرام للتحكم (Webhook من Cloudflare)
# ===========================
@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_bot():
    global DEMO, CHAT_ID

    data = request.get_json() or {}

    msg = data.get("message") or data.get("channel_post")
    if not msg:
        return {"ok": True}

    CHAT_ID = msg["chat"]["id"]
    text = msg.get("text", "").strip()

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

    elif text.startswith("/buy"):
        # مثال: /buy CS.D.EURUSD.MINI
        parts = text.split()
        if len(parts) == 2:
            epic = parts[1]
            execute_order("buy", epic)

    elif text.startswith("/sell"):
        # مثال: /sell CS.D.EURUSD.MINI
        parts = text.split()
        if len(parts) == 2:
            epic = parts[1]
            execute_order("sell", epic)

    elif text == "/start":
        tg(
            "🤖 بوت التداول جاهز.\n"
            "الأوامر:\n"
            "/demo - التحويل إلى حساب تجريبي\n"
            "/real - التحويل إلى حساب حقيقي\n"
            "/balance - عرض الرصيد\n"
            "/session - عرض بيانات الجلسة\n"
            "/buy EPIC - شراء\n"
            "/sell EPIC - بيع\n"
            "مثال:\n/buy CS.D.EURUSD.MINI"
        )

    return {"ok": True}

# ===========================
# تشغيل السيرفر
# ===========================
if __name__ == "__main__":
    login()
    app.run(host="0.0.0.0", port=8000)
