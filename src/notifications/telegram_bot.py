import base64
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

        # Command handling
        self._last_update_id = 0
        self._command_handlers = {}
        self._chat_handler = None  # Free-text chat handler
        self._polling_thread = None
        self._polling_active = False

    # ── Command system ───────────────────────────────────────────

    def register_command(self, command, handler):
        """Register a handler function for a /command."""
        self._command_handlers[command] = handler

    def register_chat_handler(self, handler):
        """Register a handler for free-text messages (non-commands).
        Handler receives (text: str) and returns a response string or None.
        """
        self._chat_handler = handler

    def start_command_listener(self):
        """Start polling for Telegram commands in a background thread."""
        if not self.enabled:
            logger.debug("Telegram disabled, skipping command listener")
            return

        self._polling_active = True
        self._polling_thread = threading.Thread(target=self._poll_updates, daemon=True)
        self._polling_thread.start()
        logger.info("Telegram command listener started")

    def stop_command_listener(self):
        """Stop the command polling thread."""
        self._polling_active = False

    def _poll_updates(self):
        """Poll Telegram for new messages/commands."""
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
        """Process a single Telegram update."""
        message = update.get("message", {})
        text = message.get("text", "") or message.get("caption", "") or ""
        chat_id = str(message.get("chat", {}).get("id", ""))

        # Only respond to the configured chat
        if chat_id != self.chat_id:
            return

        # Check for photo messages
        photos = message.get("photo", [])
        if photos and self._chat_handler:
            # Download the largest photo
            image_data = self._download_photo(photos[-1]["file_id"])
            thread = threading.Thread(
                target=self._handle_chat_async,
                args=(text or "Hvad ser du på dette billede?",),
                kwargs={"image_data": image_data},
                daemon=True,
            )
            thread.start()
            return

        if not text.startswith("/"):
            # Free-text chat message
            if self._chat_handler:
                thread = threading.Thread(
                    target=self._handle_chat_async,
                    args=(text,),
                    daemon=True,
                )
                thread.start()
            return

        parts = text.split()
        command = parts[0].split("@")[0].lower()  # handle /status@botname
        args = parts[1:]
        handler = self._command_handlers.get(command)

        if handler:
            try:
                response = handler(args)
                if response:
                    self.send(response)
            except Exception as e:
                logger.error(f"Command handler error for {command}: {e}")
                self.send(f"Fejl ved {command}: {e}")
        else:
            self.send(f"Ukendt kommando: {command}\nBrug /help for at se kommandoer.")

    def _download_photo(self, file_id):
        """Download a photo from Telegram and return base64-encoded data."""
        try:
            # Get file path
            resp = requests.get(f"{self.base_url}/getFile", params={"file_id": file_id}, timeout=10)
            if resp.status_code != 200:
                return None
            file_path = resp.json().get("result", {}).get("file_path", "")
            if not file_path:
                return None

            # Download file
            file_url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
            file_resp = requests.get(file_url, timeout=15)
            if file_resp.status_code != 200:
                return None

            return base64.b64encode(file_resp.content).decode("utf-8")
        except Exception as e:
            logger.error(f"Photo download failed: {e}")
            return None

    def _handle_chat_async(self, text, image_data=None):
        """Handle free-text chat in a background thread."""
        try:
            response = self._chat_handler(text, image_data=image_data)
            if response:
                # Chat responses are plain text from AI — never parse as HTML
                if len(response) > 4000:
                    parts = [response[i:i + 4000] for i in range(0, len(response), 4000)]
                    for part in parts:
                        self.send(part, parse_mode=None)
                else:
                    self.send(response, parse_mode=None)
        except Exception as e:
            logger.error(f"Chat handler error: {e}")
            self.send(f"Fejl i chat: {e}")

    # ── Send messages ────────────────────────────────────────────

    def send(self, message, parse_mode="HTML"):
        """Send a message to the configured Telegram chat."""
        if not self.enabled:
            logger.debug(f"Telegram disabled, would send: {message}")
            return

        try:
            payload = {
                "chat_id": self.chat_id,
                "text": message,
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode
            resp = requests.post(f"{self.base_url}/sendMessage", json=payload)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if "400" in str(e) and parse_mode == "HTML":
                # HTML parse failed (likely < > in text) — retry without parse_mode
                logger.warning(f"Telegram HTML parse failed, retrying as plain text")
                try:
                    resp2 = requests.post(f"{self.base_url}/sendMessage", json={
                        "chat_id": self.chat_id,
                        "text": message,
                    })
                    resp2.raise_for_status()
                except Exception as e2:
                    logger.error(f"Telegram send failed (plain fallback): {e2}")
            else:
                logger.error(f"Telegram send failed: {e}")
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

    def notify_trade(self, direction, epic, size, price, stop_loss, take_profit, details=None):
        """Send a trade notification with signal details."""
        emoji = "🟢" if direction == "BUY" else "🔴"
        action = "LONG" if direction == "BUY" else "SHORT"
        msg = (
            f"{emoji} <b>{action}: {epic}</b>\n"
            f"Pris: €{price:.4f}\n"
            f"Størrelse: {size}\n"
            f"Stop-loss: €{stop_loss:.4f}\n"
            f"Take-profit: €{take_profit:.4f}"
        )
        if details:
            range_pos = details.get("range_position", 0)
            zone = details.get("zone", "?")
            strength = details.get("signal_strength", 0)
            reasons = details.get("reasons", [])
            msg += f"\n\n📊 <b>Signal:</b>\n"
            msg += f"  Zone: {zone} ({range_pos:.0f}%)\n"
            msg += f"  Styrke: {strength}/9\n"
            if reasons:
                msg += f"  Grunde: {', '.join(reasons[:3])}"
        self.send(msg)

    def notify_close(self, epic, profit_loss):
        """Send a position close notification."""
        emoji = "✅" if profit_loss >= 0 else "❌"
        msg = (
            f"{emoji} <b>LUKKET: {epic}</b>\n"
            f"P/L: €{profit_loss:.2f}"
        )
        self.send(msg)

    def notify_kill_switch(self, reason):
        """Send kill switch alert."""
        msg = f"🚨 <b>KILL SWITCH AKTIVERET</b>\n{reason}\nAlle handler stoppet!"
        self.send(msg)

    def notify_status(self, balance, open_positions, daily_pl):
        """Send periodic status update."""
        msg = (
            f"📊 <b>Status opdatering</b>\n"
            f"Balance: €{balance:.2f}\n"
            f"Åbne positioner: {open_positions}\n"
            f"Daglig P/L: €{daily_pl:.2f}"
        )
        self.send(msg)

    def send_daily_summary(self, stats_engine):
        """Send daily trading summary for all bots."""
        try:
            msg = "📊 <b>Daglig Opsummering</b>\n\n"

            for bot_name in stats_engine.db_paths:
                overview = stats_engine.get_overview(bot_name)
                stats = stats_engine.get_detailed_stats(bot_name)

                emoji = "🤖" if bot_name == "rule" else "🧠"
                msg += f"{emoji} <b>{bot_name.upper()} Bot</b>\n"
                msg += f"  Trades i dag: {overview.get('today_trades', '-')}\n"
                msg += f"  Dagens P&L: EUR {overview['today_pl']:+.2f}\n"
                msg += f"  Win rate: {overview['win_rate']}%\n"
                msg += f"  Total P&L: EUR {overview['total_pl']:+.2f}\n"

                if stats['best_trade'] != 0:
                    msg += f"  Bedste: EUR {stats['best_trade']:+.2f}\n"
                if stats['worst_trade'] != 0:
                    msg += f"  Vaerste: EUR {stats['worst_trade']:+.2f}\n"

                msg += "\n"

            self.send(msg)
        except Exception as e:
            logger.error(f"Daily summary failed: {e}")

    def start_daily_summary_scheduler(self, stats_engine):
        """Schedule daily summary at 23:00 CET."""
        from datetime import datetime, timedelta

        def _schedule_next():
            now = datetime.now()
            target = now.replace(hour=23, minute=0, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            delay = (target - now).total_seconds()

            timer = threading.Timer(delay, _run_summary)
            timer.daemon = True
            timer.start()

        def _run_summary():
            self.send_daily_summary(stats_engine)
            _schedule_next()

        _schedule_next()
        logger.info("Daily summary scheduler started (23:00 CET)")
