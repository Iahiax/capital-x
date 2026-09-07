import time
import logging

logging.basicConfig(
    filename="bot.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

while True:
    try:
        from bot import app
        logging.info("Starting Flask server...")
        app.run(host="0.0.0.0", port=8000)
    except Exception as e:
        logging.error(f"Server crashed: {e}")
        time.sleep(3)
        continue
