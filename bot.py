from flask import Flask, request
import logging
from trade import execute_trade, switch_mode, current_mode

app = Flask(__name__)

DEFAULT_EPIC = "CS.D.EURUSD.MINI"

# مسار فحص حالة البوت
@app.route('/status', methods=['GET'])
def status():
    return "البوت يعمل بشكل طبيعي ✔", 200


# مسار تشغيل البوت عبر Webhook (زر تشغيل خارجي + ربط أحداث GitHub)
@app.route('/trigger', methods=['POST'])
def trigger():
    data = request.json or {}
    event = request.headers.get("X-GitHub-Event")  # نوع الحدث القادم من GitHub

    logging.info(f"GitHub Event: {event}")
    logging.info(f"Payload: {data}")

    # حدث Push → تنفيذ شراء
    if event == "push":
        execute_trade("buy", DEFAULT_EPIC)
        return "Push → Buy executed", 200

    # حدث Issue → تنفيذ بيع
    if event == "issues":
        execute_trade("sell", DEFAULT_EPIC)
        return "Issue → Sell executed", 200

    # حدث Release → التحويل إلى REAL
    if event == "release":
        switch_mode("REAL")
        return "Release → Switched to REAL", 200

    # حدث Create Tag → التحويل إلى DEMO
    if event == "create":
        if data.get("ref_type") == "tag":
            switch_mode("DEMO")
            return "Tag → Switched to DEMO", 200

    return "Event received but no action mapped", 200


# مسار TradingView Webhook
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        if not data:
            logging.error("Webhook received empty data")
            return "No data", 400

        action = data.get("action")
        epic = data.get("epic", DEFAULT_EPIC)

        if action not in ["buy", "sell"]:
            logging.error(f"Invalid action: {action}")
            return "Invalid action", 400

        logging.info(f"Webhook signal: {action} - {epic}")
        execute_trade(action, epic)

        return "OK", 200

    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return "Error", 500


# مسار Telegram Bot
@app.route('/<token>', methods=['POST'])
def telegram(token):
    try:
        update = request.json
        message = update.get("message", {})
        text = message.get("text", "")

        logging.info(f"Telegram message: {text}")

        # أوامر التداول
        if text == "/buy":
            execute_trade("buy", DEFAULT_EPIC)

        elif text == "/sell":
            execute_trade("sell", DEFAULT_EPIC)

        # أوامر تبديل الحساب
        elif text == "/demo":
            switch_mode("DEMO")
            return "تم التحويل إلى الحساب التجريبي DEMO", 200

        elif text == "/real":
            switch_mode("REAL")
            return "تم التحويل إلى الحساب الحقيقي REAL", 200

        elif text == "/mode":
            return f"الوضع الحالي: {current_mode}", 200

        # حالة البوت
        elif text == "/status":
            return "البوت يعمل بشكل طبيعي ✔", 200

        return "OK", 200

    except Exception as e:
        logging.error(f"Telegram error: {e}")
        return "Error", 500
