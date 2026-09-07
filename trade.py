import logging

def execute_trade(action, epic):
    try:
        logging.info(f"Executing trade: {action} - {epic}")

        # ضع كود Capital.com هنا
        # مثال:
        # client.open_trade(action=action, epic=epic, size=1)

        logging.info("Trade executed successfully")

    except Exception as e:
        logging.error(f"Trade error: {e}")
