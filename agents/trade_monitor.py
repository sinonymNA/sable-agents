import json
import os
from pathlib import Path

from loguru import logger

from api_client import post_to_command, send_sms

_FALLBACK = {
    "gate_day": 0,
    "gate_total": 20,
    "daily_pnl": 0.0,
    "status": "unknown",
    "last_trade": "none",
}


def _should_alert(data: dict) -> tuple[bool, list[str]]:
    reasons = []
    if float(data.get("daily_pnl", 0)) < -100:
        reasons.append(f"Daily P&L down ${abs(float(data['daily_pnl'])):,.2f}")
    if data.get("last_trade", "none") not in ("none", "", None):
        reasons.append(f"Trade fired: {data['last_trade']}")
    if data.get("status") == "halted":
        reasons.append("Trading halted")
    return bool(reasons), reasons


class TradeMonitor:
    def run(self) -> dict:
        logger.info("TradeMonitor starting")

        data_path = Path("data/trade_status.json")
        try:
            data = json.loads(data_path.read_text()) if data_path.exists() else _FALLBACK
        except Exception as exc:
            logger.error(f"TradeMonitor failed to read trade_status.json: {exc}")
            data = _FALLBACK

        gate_day = data.get("gate_day", 0)
        gate_total = data.get("gate_total", 20)
        daily_pnl = float(data.get("daily_pnl", 0))
        status = data.get("status", "unknown")
        last_trade = data.get("last_trade", "none")

        alert, reasons = _should_alert(data)

        if alert:
            reason_text = " | ".join(reasons)
            body = (
                f"[Sable Stocks Alert]\n"
                f"{reason_text}\n\n"
                f"Gate: Day {gate_day}/{gate_total}\n"
                f"Daily P&L: ${daily_pnl:+,.2f}\n"
                f"Status: {status}"
            )
            send_sms(os.environ.get("ETHAN_PHONE_NUMBER", ""), body)
            logger.info(f"TradeMonitor alert sent: {reason_text}")
        else:
            logger.info(
                f"TradeMonitor: gate {gate_day}/{gate_total}, "
                f"P&L ${daily_pnl:+,.2f}, status={status} — no alert"
            )

        payload = {
            "gate_day": gate_day,
            "gate_total": gate_total,
            "daily_pnl": daily_pnl,
            "status": status,
            "last_trade": last_trade,
            "alert_sent": alert,
            "alert_reasons": reasons,
        }
        post_to_command("trade_monitor", payload)
        return payload
