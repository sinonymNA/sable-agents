import json
import os
import re
import time
from datetime import date

from anthropic import Anthropic
from loguru import logger

from api_client import post_to_command, send_sms

_MODEL = "claude-sonnet-4-6"

_CATEGORIES = [
    ("home_kitchen",     ["air fryer accessories", "kitchen gadgets 2026", "smart home devices", "electric kettle"]),
    ("fitness_wellness", ["foam roller", "resistance bands", "massage gun", "red light therapy"]),
    ("pet_products",     ["dog enrichment toys", "cat water fountain", "pet camera", "dog anxiety vest"]),
    ("tech_accessories", ["phone stand", "wireless charger", "laptop stand", "cable organizer"]),
    ("outdoor_travel",   ["portable charger", "travel pillow", "hiking gear", "camping gadgets"]),
    ("beauty_skincare",  ["gua sha", "ice roller", "LED face mask", "electric lash curler"]),
]

_SYSTEM = """You are a dropshipping product intelligence analyst for Sable Agents.
You receive Google Trends interest scores (0-100) for product search terms over the last 3 months.
Identify the top 3 rising opportunities with genuine dropshipping potential.

Criteria:
- Search interest is increasing (rising momentum, not just high)
- Sourceable from AliExpress/CJ Dropshipping for under $15 landed cost
- Retail price point $25-$80 (50%+ margin target)
- Not already saturated by Amazon private label

Respond ONLY in this JSON, no preamble, no markdown fences:
{
  "opportunities": [
    {
      "product_name": "string",
      "category": "string",
      "trend_score": 0,
      "trend_direction": "rising|stable|declining",
      "estimated_retail_price": "string",
      "estimated_cogs": "string",
      "margin_note": "string",
      "why_now": "string",
      "shopify_title_suggestion": "string",
      "one_line_hook": "string"
    }
  ],
  "scan_summary": "string"
}"""


def _fetch_trends_data() -> dict:
    try:
        from pytrends.request import TrendReq
    except ImportError:
        logger.error("pytrends not installed")
        return {}

    results: dict = {}
    pytrends = TrendReq(hl="en-US", tz=300)

    for label, terms in _CATEGORIES:
        try:
            pytrends.build_payload(terms[:4], timeframe="today 3-m")
            df = pytrends.interest_over_time()
            if df is not None and not df.empty:
                category_scores: dict = {}
                for term in terms[:4]:
                    if term in df.columns:
                        current = int(df[term].iloc[-1])
                        four_weeks_ago = int(df[term].iloc[-4]) if len(df) >= 4 else current
                        momentum = current - four_weeks_ago
                        category_scores[term] = {"current": current, "momentum": momentum}
                results[label] = category_scores
            time.sleep(2)
        except Exception as exc:
            logger.warning(f"pytrends fetch failed for {label}: {exc}")
            results[label] = {}

    return results


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text.strip())
    return json.loads(text)


class TrendsScout:
    def run(self, product_hint: str | None = None) -> dict:
        logger.info("--- TrendsScout starting ---")
        result: dict = {"opportunities": [], "scan_summary": "", "status": "error"}

        try:
            if product_hint:
                user_payload = {
                    "product_hint": product_hint,
                    "note": "Ethan specifically requested analysis for this product. Prioritize it and find 2-3 related opportunities.",
                    "scan_date": date.today().isoformat(),
                }
            else:
                trends_data = _fetch_trends_data()
                user_payload = {
                    "trends_data": trends_data,
                    "scan_date": date.today().isoformat(),
                }

            client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
            message = client.messages.create(
                model=_MODEL,
                max_tokens=1200,
                system=_SYSTEM,
                messages=[{"role": "user", "content": json.dumps(user_payload)}],
            )
            result = _parse_json(message.content[0].text)
            result["opportunities"] = result.get("opportunities", [])[:3]
            result["status"] = "success"

            lines = ["Sable Trends — Top Dropshipping Finds:\n"]
            for i, opp in enumerate(result["opportunities"], 1):
                lines.append(
                    f"{i}. {opp['product_name']}\n"
                    f"   Why now: {opp['why_now']}\n"
                    f"   Retail ~{opp['estimated_retail_price']} | {opp['margin_note']}"
                )
            lines.append("\nText SHOP [product name] to create a listing.\n— Sable")
            body = "\n".join(lines)

        except Exception as exc:
            logger.error(f"TrendsScout failed: {exc}")
            body = "TrendsScout scan failed — check Railway logs.\n— Sable"
            result["status"] = "error"

        send_sms(os.environ.get("ETHAN_PHONE_NUMBER", ""), body)
        post_to_command("trends_scout", {**result, "product_hint": product_hint})
        logger.info("--- TrendsScout complete ---")
        return result
