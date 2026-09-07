import requests
import json
import logging

EMAIL = "yahia.x@outlook.sa"
API_KEY = "ut2RpxSbx6fiDdHv"
API_KEY_PASSWORD = "Yahia@1411"

# الوضع الافتراضي
current_mode = "DEMO"

def get_server():
    if current_mode == "DEMO":
        return "https://demo-api-capital.backend-capital.com"
    else:
        return "https://api-capital.backend-capital.com"

SERVER = get_server()

headers = {
    "X-CAP-API-KEY": API_KEY,
    "Content-Type": "application/json"
}

CST = None
XST = None


def switch_mode(mode):
    global current_mode, SERVER, CST, XST
    current_mode = mode
    SERVER = get_server()
    CST = None
    XST = None
    logging.info(f"Switched mode to: {current_mode}")


def login():
    global CST, XST

    try:
        url = f"{SERVER}/api/v1/session"

        payload = {
            "identifier": EMAIL,
            "password": API_KEY_PASSWORD,
            "encryptedPassword": False
        }

        r = requests.post(url, headers=headers, data=json.dumps(payload))

        if r.status_code != 200:
            logging.error(f"Login failed: {r.text}")
            return False

        CST = r.headers.get("CST")
        XST = r.headers.get("X-SECURITY-TOKEN")

        logging.info(f"Capital.com login successful ({current_mode})")
        return True

    except Exception as e:
        logging.error(f"Login error: {e}")
        return False


def execute_trade(action, epic):
    global CST, XST

    try:
        if CST is None or XST is None:
            if not login():
                logging.error("Cannot execute trade: login failed")
                return

        url = f"{SERVER}/api/v1/positions"

        headers2 = {
            "CST": CST,
            "X-SECURITY-TOKEN": XST,
            "Content-Type": "application/json"
        }

        direction = "BUY" if action == "buy" else "SELL"

        payload = {
            "epic": epic,
            "direction": direction,
            "size": 1,
            "orderType": "MARKET",
            "guaranteedStop": False
        }

        r = requests.post(url, headers=headers2, data=json.dumps(payload))

        if r.status_code == 200:
            logging.info(f"Trade executed: {action} - {epic} ({current_mode})")
        else:
            logging.error(f"Trade failed: {r.text}")

    except Exception as e:
        logging.error(f"Trade error: {e}")
