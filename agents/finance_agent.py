import json
import os
from pathlib import Path

from anthropic import Anthropic
from loguru import logger

from api_client import post_to_command, send_sms

_SYSTEM = """You are Sable Brain, the intelligence engine for Sable Agents.

Mission: Grow revenue to $50K/month by 2027.
Products: FreshUp AI ($399/month/location), Sable Stocks (automated trading).
Team: Ethan (COO), JT (CSO), Tyler (CFO).

You are generating the weekly P&L summary for Tyler (CFO).

Format it as a clean, professional financial summary:
- Week
- Income: $X
- Expenses: $X
- Net: $X (profit or loss)
- One-line observation about trajectory or next focus

Keep it concise and factual. This is a text message, not a report."""

_FALLBACK = {"week": "unknown", "income": 0, "expenses": 0, "notes": "No data available."}


class FinanceAgent:
    def run(self) -> str:
        logger.info("FinanceAgent starting")

        data_path = Path("data/finance.json")
        try:
            finance_data = json.loads(data_path.read_text()) if data_path.exists() else _FALLBACK
        except Exception as exc:
            logger.error(f"FinanceAgent failed to read finance.json: {exc}")
            finance_data = _FALLBACK

        net = finance_data.get("income", 0) - finance_data.get("expenses", 0)

        try:
            client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
            message = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=512,
                system=_SYSTEM,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Generate the weekly P&L summary from this data:\n"
                        f"{json.dumps(finance_data)}\n"
                        f"Calculated net: ${net:,.2f}"
                    ),
                }],
            )
            summary = message.content[0].text.strip()
        except Exception as exc:
            logger.error(f"FinanceAgent Claude call failed: {exc}")
            week = finance_data.get("week", "unknown")
            summary = (
                f"Week: {week}\n"
                f"Income: ${finance_data.get('income', 0):,.2f}\n"
                f"Expenses: ${finance_data.get('expenses', 0):,.2f}\n"
                f"Net: ${net:,.2f}\n"
                f"Notes: {finance_data.get('notes', '')}"
            )

        body = f"Weekly P&L — {finance_data.get('week', '')}:\n\n{summary}\n\n— Sable"
        send_sms(os.environ.get("TYLER_PHONE_NUMBER", ""), body)
        post_to_command("finance_agent", {"summary": summary, "data": finance_data, "status": "sent"})
        logger.info("FinanceAgent complete")
        return summary
