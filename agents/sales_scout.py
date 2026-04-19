import os

from anthropic import Anthropic
from loguru import logger

from api_client import post_to_command, send_sms

_SYSTEM = """You are Sable Brain, the intelligence engine for Sable Agents.

Mission: Grow revenue to $50K/month by 2027.
Products: FreshUp AI ($399/month/location — AI phone sales training simulator for automotive dealerships), Sable Stocks (automated trading system).
Team: Ethan (COO), JT (CSO — handles all FreshUp sales), Tyler (CFO).

You are generating JT's morning sales briefing. JT is the Chief Sales Officer selling FreshUp AI to automotive dealerships.

FreshUp AI solves a specific pain: dealership sales reps forget their training within weeks, managers can't run role-plays at scale, and phone skills are the #1 factor in appointment conversion. FreshUp fixes this with an AI simulator that reps can practice with anytime.

Generate exactly 3 items. Each item must be:
- A specific action JT can take TODAY (a call script line, an objection handle, a target dealership type, a follow-up move)
- Grounded in real dealership sales psychology
- Under 3 sentences

Format as:
1. [action]
2. [action]
3. [action]

This will be sent as a text message. Keep the total under 300 characters per item."""


class SalesScout:
    def run(self) -> str:
        logger.info("SalesScout starting")
        try:
            client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
            message = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=512,
                system=_SYSTEM,
                messages=[{
                    "role": "user",
                    "content": "Generate today's 3-item FreshUp sales briefing for JT.",
                }],
            )
            briefing = message.content[0].text.strip()
        except Exception as exc:
            logger.error(f"SalesScout Claude call failed: {exc}")
            briefing = "SalesScout unavailable today. Check ANTHROPIC_API_KEY."

        body = f"JT — Morning Sales Brief:\n\n{briefing}\n\n— Sable"
        send_sms(os.environ.get("JT_PHONE_NUMBER", ""), body)
        post_to_command("sales_scout", {"briefing": briefing, "status": "sent"})
        logger.info("SalesScout complete")
        return briefing
