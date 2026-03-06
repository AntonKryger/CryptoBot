import logging
import requests

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send trade notifications via Telegram."""

    def __init__(self, config):
        tg_cfg = config.get("telegram", {})
        self.enabled = tg_cfg.get("enabled", False)
        self.bot_token = tg_cfg.get("bot_token", "")
        self.chat_id = tg_cfg.get("chat_id", "")
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def send(self, message):
        """Send a message to the configured Telegram chat."""
        if not self.enabled:
            logger.debug(f"Telegram disabled, would send: {message}")
            return

        try:
            resp = requests.post(f"{self.base_url}/sendMessage", json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
            })
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

    def notify_trade(self, direction, epic, size, price, stop_loss, take_profit):
        """Send a trade notification."""
        emoji = "🟢" if direction == "BUY" else "🔴"
        action = "LONG" if direction == "BUY" else "SHORT"
        msg = (
            f"{emoji} <b>{action}: {epic}</b>\n"
            f"Størrelse: {size}\n"
            f"Pris: €{price:.2f}\n"
            f"Stop-loss: €{stop_loss:.2f}\n"
            f"Take-profit: €{take_profit:.2f}"
        )
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
