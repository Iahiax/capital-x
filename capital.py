"""Capital.com <-> Telegram trading bot.

Safety defaults:
- DEMO mode is the default.
- Live mode is disabled unless ENABLE_LIVE_MODE=true.
- Orders use a fixed configured size; the bot never derives order size from balance.
- Credentials are loaded from environment variables, never hard-coded.

Expected Telegram signal JSON:
{"action":"reverse","signal":"BUY","timestamp":1710000000}
"""

from __future__ import annotations

import json
import logging
import os
import signal as os_signal
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# -----------------------------
# Configuration
# -----------------------------

load_dotenv()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"متغير البيئة المطلوب غير موجود: {name}")
    return value


@dataclass
class Config:
    capital_email: str
    capital_api_key: str
    capital_api_password: str
    telegram_token: str
    telegram_chat_id: str
    mode: str
    epic: str
    order_size: float
    max_order_size: float
    poll_seconds: float
    request_timeout: float
    enable_live_mode: bool
    send_telegram_replies: bool

    @classmethod
    def from_env(cls) -> "Config":
        mode = os.getenv("CAPITAL_MODE", "DEMO").strip().upper()
        if mode not in {"DEMO", "REAL"}:
            raise RuntimeError("CAPITAL_MODE يجب أن تكون DEMO أو REAL")

        order_size = float(os.getenv("ORDER_SIZE", "1"))
        max_order_size = float(os.getenv("MAX_ORDER_SIZE", "1"))
        if order_size <= 0 or max_order_size <= 0 or order_size > max_order_size:
            raise RuntimeError("تحقق من ORDER_SIZE وMAX_ORDER_SIZE؛ يجب أن يكون الحجم موجبًا ولا يتجاوز الحد")

        return cls(
            capital_email=required_env("CAPITAL_EMAIL"),
            capital_api_key=required_env("CAPITAL_API_KEY"),
            capital_api_password=required_env("CAPITAL_API_PASSWORD"),
            telegram_token=required_env("TELEGRAM_TOKEN"),
            telegram_chat_id=required_env("TELEGRAM_CHAT_ID"),
            mode=mode,
            epic=os.getenv("CAPITAL_EPIC", "CS.D.EURUSD.MINI").strip(),
            order_size=order_size,
            max_order_size=max_order_size,
            poll_seconds=float(os.getenv("POLL_SECONDS", "1")),
            request_timeout=float(os.getenv("REQUEST_TIMEOUT", "20")),
            enable_live_mode=env_bool("ENABLE_LIVE_MODE", False),
            send_telegram_replies=env_bool("SEND_TELEGRAM_REPLIES", True),
        )


# -----------------------------
# Logging and HTTP helpers
# -----------------------------

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
LOGGER = logging.getLogger("capital-telegram-bot")


def build_http_session() -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST", "DELETE"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.headers.update({"Accept": "application/json"})
    return session


def response_json(response: requests.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"استجابة غير JSON من الخادم: HTTP {response.status_code}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("صيغة الاستجابة غير متوقعة")
    return data


# -----------------------------
# Capital.com client
# -----------------------------

class CapitalClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.http = build_http_session()
        self.cst: Optional[str] = None
        self.security_token: Optional[str] = None

    @property
    def base_url(self) -> str:
        # Correct official endpoints. The LIVE URL must not contain a repeated domain segment.
        if self.config.mode == "DEMO":
            return "https://demo-api-capital.backend-capital.com"
        return "https://api-capital.backend-capital.com"

    def _auth_headers(self) -> dict[str, str]:
        if not self.cst or not self.security_token:
            raise RuntimeError("لا توجد جلسة Capital.com صالحة")
        return {"CST": self.cst, "X-SECURITY-TOKEN": self.security_token}

    def login(self) -> None:
        url = f"{self.base_url}/api/v1/session"
        payload = {
            "identifier": self.config.capital_email,
            "password": self.config.capital_api_password,
            "encryptedPassword": False,
        }
        headers = {
            "X-CAP-API-KEY": self.config.capital_api_key,
            "Content-Type": "application/json",
        }
        response = self.http.post(
            url,
            headers=headers,
            json=payload,
            timeout=self.config.request_timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"فشل تسجيل الدخول إلى Capital.com: HTTP {response.status_code} - {response.text[:300]}")

        cst = response.headers.get("CST")
        security_token = response.headers.get("X-SECURITY-TOKEN")
        if not cst or not security_token:
            raise RuntimeError("تم قبول تسجيل الدخول دون وصول CST أو X-SECURITY-TOKEN")
        self.cst = cst
        self.security_token = security_token
        LOGGER.info("تم تسجيل الدخول إلى Capital.com في وضع %s", self.config.mode)

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        response = self.http.request(
            method,
            f"{self.base_url}{path}",
            headers={**self._auth_headers(), **kwargs.pop("headers", {})},
            timeout=self.config.request_timeout,
            **kwargs,
        )
        if response.status_code in {401, 403}:
            LOGGER.warning("انتهت جلسة Capital.com؛ ستتم إعادة تسجيل الدخول")
            self.login()
            response = self.http.request(
                method,
                f"{self.base_url}{path}",
                headers={**self._auth_headers(), **kwargs.pop("headers", {})},
                timeout=self.config.request_timeout,
                **kwargs,
            )
        return response

    def get_account_info(self) -> dict[str, Any]:
        response = self._request("GET", "/api/v1/accounts")
        if response.status_code >= 400:
            raise RuntimeError(f"فشل جلب الحسابات: HTTP {response.status_code} - {response.text[:300]}")
        return response_json(response)

    def get_available_balance(self) -> float:
        data = self.get_account_info()
        try:
            return float(data["accountInfo"]["available"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"بنية الرصيد غير متوقعة: {data}") from exc

    def list_positions(self) -> list[dict[str, Any]]:
        response = self._request("GET", "/api/v1/positions")
        if response.status_code >= 400:
            raise RuntimeError(f"فشل جلب الصفقات: HTTP {response.status_code} - {response.text[:300]}")
        data = response_json(response)
        positions = data.get("positions", [])
        if not isinstance(positions, list):
            raise RuntimeError("بنية positions غير متوقعة")
        return positions

    @staticmethod
    def position_fields(item: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
        # Current API responses normally nest trade data under position.
        nested = item.get("position") if isinstance(item.get("position"), dict) else {}
        deal_id = nested.get("dealId") or item.get("dealId") or item.get("positionId")
        direction = nested.get("direction") or item.get("direction")
        return (str(deal_id) if deal_id else None, str(direction).upper() if direction else None)

    def close_positions_by_direction(self, direction: str) -> int:
        direction = direction.upper()
        closed = 0
        for item in self.list_positions():
            if not isinstance(item, dict):
                continue
            deal_id, position_direction = self.position_fields(item)
            if deal_id and position_direction == direction:
                # Official close operation: DELETE /api/v1/positions/{dealId}.
                response = self._request("DELETE", f"/api/v1/positions/{deal_id}")
                if response.status_code >= 400:
                    raise RuntimeError(
                        f"فشل إغلاق الصفقة {deal_id}: HTTP {response.status_code} - {response.text[:300]}"
                    )
                LOGGER.info("تم إغلاق الصفقة %s", deal_id)
                closed += 1
        return closed

    def open_position(self, direction: str) -> dict[str, Any]:
        direction = direction.upper()
        if direction not in {"BUY", "SELL"}:
            raise ValueError("اتجاه الصفقة يجب أن يكون BUY أو SELL")
        if self.config.order_size > self.config.max_order_size:
            raise RuntimeError("حجم الصفقة يتجاوز الحد الأقصى المسموح")

        payload = {
            "direction": direction,
            "epic": self.config.epic,
            "size": self.config.order_size,
        }
        response = self._request("POST", "/api/v1/positions", json=payload)
        if response.status_code >= 400:
            raise RuntimeError(f"فشل فتح الصفقة: HTTP {response.status_code} - {response.text[:300]}")
        data = response_json(response)
        LOGGER.info("تم إرسال أمر %s على %s بحجم %s", direction, self.config.epic, self.config.order_size)
        return data

    def reverse_position(self, signal: str) -> tuple[int, dict[str, Any]]:
        signal = signal.upper()
        if signal == "BUY":
            closed = self.close_positions_by_direction("SELL")
        elif signal == "SELL":
            closed = self.close_positions_by_direction("BUY")
        else:
            raise ValueError("الإشارة يجب أن تكون BUY أو SELL")
        opened = self.open_position(signal)
        return closed, opened


# -----------------------------
# Telegram client
# -----------------------------

class TelegramClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.http = build_http_session()
        self.base_url = f"https://api.telegram.org/bot{config.telegram_token}"
        self.offset: Optional[int] = None

    def get_updates(self) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "timeout": max(1, int(self.config.poll_seconds)),
            "allowed_updates": json.dumps(["message"]),
        }
        if self.offset is not None:
            params["offset"] = self.offset
        response = self.http.get(
            f"{self.base_url}/getUpdates",
            params=params,
            timeout=self.config.request_timeout + max(1, int(self.config.poll_seconds)),
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Telegram getUpdates فشل: HTTP {response.status_code}")
        data = response_json(response)
        if not data.get("ok"):
            raise RuntimeError(f"Telegram أعاد خطأ: {data}")
        result = data.get("result", [])
        return result if isinstance(result, list) else []

    def send_message(self, text: str) -> None:
        if not self.config.send_telegram_replies:
            return
        response = self.http.post(
            f"{self.base_url}/sendMessage",
            json={"chat_id": self.config.telegram_chat_id, "text": text[:4000]},
            timeout=self.config.request_timeout,
        )
        if response.status_code >= 400:
            LOGGER.warning("تعذر إرسال رد Telegram: HTTP %s", response.status_code)


# -----------------------------
# Signal validation and runner
# -----------------------------


def parse_timestamp(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
    raise ValueError("timestamp غير صالح")


def parse_signal(text: str) -> Optional[dict[str, Any]]:
    try:
        data = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("action") != "reverse":
        return None
    signal_value = str(data.get("signal", "")).upper()
    if signal_value not in {"BUY", "SELL"}:
        return None
    if "timestamp" not in data:
        return None
    data["signal"] = signal_value
    data["timestamp"] = parse_timestamp(data["timestamp"])
    return data


def is_allowed_chat(message: dict[str, Any], allowed_chat_id: str) -> bool:
    chat = message.get("chat") or {}
    return str(chat.get("id", "")) == allowed_chat_id


def process_update(
    update: dict[str, Any],
    config: Config,
    capital: CapitalClient,
    telegram: TelegramClient,
    last_signal_timestamp: Optional[float],
) -> Optional[float]:
    msg = update.get("message") or update.get("channel_post")
    message = msg if isinstance(msg, dict) else {}
    if not message or not is_allowed_chat(message, config.telegram_chat_id):
        LOGGER.warning("تم تجاهل رسالة من chat_id غير مصرح به")
        return last_signal_timestamp

    text = str(message.get("text", "")).strip()
    if text == "/status":
        balance = capital.get_available_balance()
        telegram.send_message(f"الوضع: {config.mode}\nالأداة: {config.epic}\nالرصيد المتاح: {balance}")
        return last_signal_timestamp

    if text == "/demo":
        capital.config.mode = "DEMO"
        capital.login()
        telegram.send_message("تم التحويل إلى DEMO")
        return last_signal_timestamp

    if text in {"/real", "/real CONFIRM"}:
        if not capital.config.enable_live_mode:
            telegram.send_message("الحساب الحقيقي معطل. غيّر ENABLE_LIVE_MODE=true بعد مراجعة الإعدادات.")
            return last_signal_timestamp
        if text != "/real CONFIRM":
            telegram.send_message("للتفعيل المؤقت استخدم /real CONFIRM فقط بعد مراجعة المخاطر.")
            return last_signal_timestamp
        capital.config.mode = "REAL"
        capital.login()
        telegram.send_message("تم التحويل إلى REAL. راجع الحجم والحدود قبل إرسال أي إشارة.")
        return last_signal_timestamp

    parsed = parse_signal(text)
    if not parsed:
        return last_signal_timestamp

    timestamp = float(parsed["timestamp"])
    if last_signal_timestamp is not None and timestamp <= last_signal_timestamp:
        LOGGER.info("تم تجاهل إشارة قديمة أو مكررة")
        return last_signal_timestamp

    signal_value = parsed["signal"]
    closed, opened = capital.reverse_position(signal_value)
    telegram.send_message(
        f"تم تنفيذ {signal_value}\nالأداة: {config.epic}\nالحجم: {config.order_size}\n"
        f"الصفقات المغلقة: {closed}\nرد الفتح: {json.dumps(opened, ensure_ascii=False)[:1000]}"
    )
    return timestamp


def main() -> None:
    config = Config.from_env()
    if config.mode == "REAL" and not config.enable_live_mode:
        raise RuntimeError("REAL مرفوض افتراضيًا. استخدم ENABLE_LIVE_MODE=true بعد مراجعة المخاطر.")

    capital = CapitalClient(config)
    telegram = TelegramClient(config)
    capital.login()
    telegram.send_message(f"بدأ البوت في وضع {config.mode} على {config.epic}")

    stop_requested = False

    def request_stop(signum: int, _frame: Any) -> None:
        nonlocal stop_requested
        stop_requested = True
        LOGGER.info("استلام إشارة إيقاف: %s", signum)

    os_signal.signal(os_signal.SIGINT, request_stop)
    os_signal.signal(os_signal.SIGTERM, request_stop)

    last_signal_timestamp: Optional[float] = None
    while not stop_requested:
        try:
            updates = telegram.get_updates()
            for update in updates:
                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    telegram.offset = update_id + 1
                try:
                    last_signal_timestamp = process_update(
                        update,
                        config,
                        capital,
                        telegram,
                        last_signal_timestamp,
                    )
                except Exception as exc:  # Keep polling after one malformed signal/order.
                    LOGGER.exception("فشل التعامل مع تحديث Telegram: %s", exc)
                    telegram.send_message(f"فشل تنفيذ التحديث: {str(exc)[:500]}")
        except requests.RequestException as exc:
            LOGGER.warning("خطأ شبكة؛ إعادة المحاولة بعد قليل: %s", exc)
            time.sleep(min(30, max(2, config.poll_seconds * 2)))
        except Exception as exc:
            LOGGER.exception("خطأ في الحلقة الرئيسية: %s", exc)
            time.sleep(min(30, max(2, config.poll_seconds * 2)))

    LOGGER.info("تم إيقاف البوت بأمان")


if __name__ == "__main__":
    main()
