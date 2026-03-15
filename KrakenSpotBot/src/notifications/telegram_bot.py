"""
Telegram notifications for KrakenBots.
Simplified version — uses Coach bot token for notifications.
"""

import logging
import requests
import threading
import time

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send trade notifications and handle commands via Telegram."""

    def __init__(self, config):
        tg_cfg = config.get("telegram", {})
        self.enabled = tg_cfg.get("enabled", False)
        self.bot_token = tg_cfg.get("bot_token", "")
        self.chat_id = tg_cfg.get("chat_id", "")
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.bot_id = config.get("bot", {}).get("id", "BOT")

        self._last_update_id = 0
        self._command_handlers = {}
        self._polling_thread = None
        self._polling_active = False

    def register_command(self, command, handler):
        self._command_handlers[command] = handler

    def start_command_listener(self):
        if not self.enabled:
            return
        self._polling_active = True
        self._polling_thread = threading.Thread(target=self._poll_updates, daemon=True)
        self._polling_thread.start()
        logger.info("Telegram command listener started")

    def stop_command_listener(self):
        self._polling_active = False

    def _poll_updates(self):
        while self._polling_active:
            try:
                resp = requests.get(f"{self.base_url}/getUpdates", params={
                    "offset": self._last_update_id + 1,
                    "timeout": 10,
                }, timeout=15)

                if resp.status_code != 200:
                    time.sleep(5)
                    continue

                data = resp.json()
                for update in data.get("result", []):
                    self._last_update_id = update["update_id"]
                    self._handle_update(update)
            except Exception as e:
                logger.error(f"Telegram polling error: {e}")
                time.sleep(5)

    def _handle_update(self, update):
        message = update.get("message", {})
        text = message.get("text", "") or ""
        chat_id = str(message.get("chat", {}).get("id", ""))

        if chat_id != self.chat_id:
            return

        if not text.startswith("/"):
            return

        parts = text.split()
        command = parts[0].split("@")[0].lower()
        args = parts[1:]
        handler = self._command_handlers.get(command)

        if handler:
            try:
                response = handler(args)
                if response:
                    self.send(response)
            except Exception as e:
                self.send(f"Error: {e}")
        else:
            self.send(f"Unknown command: {command}")

    def send(self, message, parse_mode="HTML", prefix=True):
        if not self.enabled:
            logger.debug(f"Telegram disabled, would send: {message}")
            return

        if prefix and self.bot_id:
            message = f"[{self.bot_id}] {message}"

        try:
            payload = {"chat_id": self.chat_id, "text": message}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            resp = requests.post(f"{self.base_url}/sendMessage", json=payload)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if "400" in str(e) and parse_mode == "HTML":
                try:
                    requests.post(f"{self.base_url}/sendMessage", json={
                        "chat_id": self.chat_id, "text": message,
                    }).raise_for_status()
                except Exception as e2:
                    logger.error(f"Telegram send failed (fallback): {e2}")
            else:
                logger.error(f"Telegram send failed: {e}")
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

    def notify_trade(self, direction, epic, size, price, stop_loss, take_profit, details=None):
        emoji = "🟢" if direction == "BUY" else "🔴"
        action = "LONG" if direction == "BUY" else "SHORT"
        msg = (
            f"{emoji} <b>{action}: {epic}</b>\n"
            f"Price: ${price:.2f}\n"
            f"Size: {size}\n"
            f"SL: ${stop_loss:.2f}\n"
            f"TP: ${take_profit:.2f}"
        )
        if details:
            strategy = details.get("signal_type", "?")
            reasons = details.get("reasons", [])
            msg += f"\n\n📊 Strategy: {strategy}"
            if reasons:
                msg += f"\n{', '.join(reasons[:3])}"
        self.send(msg)

    def notify_close(self, epic, profit_loss):
        emoji = "✅" if profit_loss >= 0 else "❌"
        self.send(f"{emoji} <b>CLOSED: {epic}</b>\nP/L: ${profit_loss:.2f}")

    def notify_kill_switch(self, reason):
        self.send(f"🚨 <b>KILL SWITCH</b>\n{reason}")

    def notify_regime_shift(self, epic, old_regime, new_regime, active_bot):
        self.send(
            f"🔄 <b>Regime shift: {epic}</b>\n"
            f"{old_regime} → {new_regime}\n"
            f"Active bot: {active_bot}"
        )
