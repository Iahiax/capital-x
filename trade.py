import requests
import json
import logging

EMAIL = "yahia.x@outlook.sa"
API_KEY = "ut2RpxSbx6fiDdHv"
API_KEY_PASSWORD = "Yahia@1411"
DEMO = True

SERVER = "https://demo-api-capital.backend-capital.com" if DEMO else "https://api-capital.backend-capital.com"

headers = {
    "X-CAP-API-KEY": API_KEY,
    "Content-Type": "application/json"
}

CST = None
XST = None


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

        logging.info("Capital.com login successful")
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
            logging.info(f"Trade executed: {action} - {epic}")
        else:
            logging.error(f"Trade failed: {r.text}")

    except Exception as e:
        logging.error(f"Trade error: {e}")
