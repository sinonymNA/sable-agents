import json
import os
import re
import time
from typing import Any

import anthropic
import httpx
from loguru import logger

from db.models import log_agent_run

_SYSTEM = """You are Sable Finance, the financial intelligence agent for Sable. You track \
every dollar across all income streams and give Ethan, a 22-year-old AP History teacher \
and entrepreneur, a clear honest picture of where the money is each morning.

His goals: $20K/month by 25, generational wealth by 30.
Foundation: save 20% of Sable income.

Be direct. If numbers are small, say so without apology but connect small numbers to \
trajectory. $4 paper trading profit is proof of a mechanism, not the mechanism.

Respond ONLY in this JSON structure, no preamble, no markdown:
{
  "daily_total": float,
  "monthly_total": float,
  "goal_progress_pct": float,
  "foundation_contribution": float,
  "breakdown": {
    "sable_stocks": {"daily": float, "monthly": float, "gate_day": int, "gate_passed": bool, "status": str},
    "freshup": {"daily": float, "monthly": float, "status": str}
  },
  "trajectory_note": str,
  "spoken_summary": str
}"""


def _fetch_revenue(base_url: str, secret: str, name: str) -> dict:
    if not base_url:
        return {"daily": 0.0, "monthly": 0.0, "status": f"{name} API URL not configured"}
    try:
        resp = httpx.get(
            f"{base_url}/api/revenue",
            headers={"X-Dashboard-Secret": secret},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning(f"{name} revenue fetch failed: {exc}")
        return {"daily": 0.0, "monthly": 0.0, "status": f"error: {exc}"}


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text.strip())
    return json.loads(text)


class SableFinance:
    def run(self) -> dict[str, Any]:
        start = time.time()

        stocks_data = _fetch_revenue(
            os.environ.get("SABLE_STOCKS_API_URL", ""),
            os.environ.get("SABLE_STOCKS_SECRET", ""),
            "Sable Stocks",
        )
        freshup_data = _fetch_revenue(
            os.environ.get("FRESHUP_API_URL", ""),
            os.environ.get("FRESHUP_SECRET", ""),
            "FreshUp",
        )

        stocks_daily = float(stocks_data.get("daily", 0))
        stocks_monthly = float(stocks_data.get("monthly", 0))
        freshup_daily = float(freshup_data.get("daily", 0))
        freshup_monthly = float(freshup_data.get("monthly", 0))

        total_daily = stocks_daily + freshup_daily
        total_monthly = stocks_monthly + freshup_monthly
        goal_progress = (total_monthly / 10000) * 100
        foundation = total_monthly * 0.20

        revenue_payload = {
            "sable_stocks": {"daily": stocks_daily, "monthly": stocks_monthly, "raw": stocks_data},
            "freshup": {"daily": freshup_daily, "monthly": freshup_monthly, "raw": freshup_data},
            "totals": {
                "daily": total_daily,
                "monthly": total_monthly,
                "goal_progress_pct": goal_progress,
                "foundation_contribution": foundation,
            },
        }

        result: dict[str, Any] = {
            "daily_total": total_daily,
            "monthly_total": total_monthly,
            "goal_progress_pct": goal_progress,
            "foundation_contribution": foundation,
            "breakdown": {
                "sable_stocks": {
                    "daily": stocks_daily,
                    "monthly": stocks_monthly,
                    "gate_day": stocks_data.get("gate_day", 0),
                    "gate_passed": stocks_data.get("gate_passed", False),
                    "status": stocks_data.get("status", "unknown"),
                },
                "freshup": {
                    "daily": freshup_daily,
                    "monthly": freshup_monthly,
                    "status": freshup_data.get("status", "unknown"),
                },
            },
            "trajectory_note": "",
            "spoken_summary": "",
        }

        status = "success"
        try:
            client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=_SYSTEM,
                messages=[{"role": "user", "content": json.dumps(revenue_payload)}],
            )
            parsed = _parse_json(message.content[0].text)
            result.update(parsed)
            logger.info("Finance agent completed")
        except Exception as exc:
            status = "error"
            result["spoken_summary"] = str(exc)
            logger.error(f"Finance agent error: {exc}")

        duration = round(time.time() - start, 2)
        log_agent_run(
            "finance", status,
            result.get("spoken_summary", "")[:300],
            json.dumps(result),
            duration,
        )
        return result
