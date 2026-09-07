from flask import Flask, request
import logging
from trade import execute_trade, switch_mode, current_mode

app = Flask(__name__)

DEFAULT_EPIC = "CS.D.EURUSD.MINI"

# مسار فحص حالة البوت
@app.route('/status', methods=['GET'])
def status():
    return "البوت يعمل بشكل طبيعي ✔", 200


# مسار تشغيل البوت عبر Webhook (زر تشغيل خارجي)
@app.route('/trigger', methods=['POST'])
def trigger():
    data = request.json or {}
    action = data.get("action")

    logging.info(f"Trigger received: {data}")

    if action == "buy":
        execute_trade("buy", DEFAULT_EPIC)
        return "Buy executed", 200

    if action == "sell":
        execute_trade("sell", DEFAULT_EPIC)
        return "Sell executed", 200

    if action == "demo":
        switch_mode("DEMO")
        return "Switched to DEMO", 200

    if action == "real":
        switch_mode("REAL")
        return "Switched to REAL", 200

    return "Unknown action", 400


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
