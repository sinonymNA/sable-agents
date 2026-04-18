import json
import os
import re
import time
from typing import Any

import anthropic
import httpx
from loguru import logger

from db.models import log_agent_run

_SYSTEM = """You are Sable Business, the market intelligence agent for Sable. Your job is to \
find market gaps and evaluate opportunities for Ethan Seligman, a 22-year-old AP History \
teacher and entrepreneur in Atlanta, Georgia.

His assets: AI/ML expertise since 2020, teaching credibility, FreshUp AI (AI sales trainer \
for dealerships, JT handles sales), Sable Stocks (automated trading), growing Substack, \
strong builder skills.

JT is his brother-in-law and sales partner for FreshUp. Alert Ethan to anything relevant \
for JT to know.

Never recommend things requiring significant upfront capital. Always connect to existing \
assets. Be specific, not theoretical.

Respond ONLY in this JSON, no preamble, no markdown:
{
  "top_signals": [{"headline": str, "why_it_matters": str}],
  "opportunity_of_the_day": {
    "name": str,
    "description": str,
    "revenue_potential": str,
    "startup_cost": str,
    "connection_to_ethan": str,
    "recommended_action": str
  },
  "jt_alert": str,
  "watch_list": [str],
  "spoken_summary": str
}"""


def _fetch_news() -> list[str]:
    newsapi_key = os.environ.get("NEWSAPI_KEY", "")
    if newsapi_key:
        try:
            resp = httpx.get(
                "https://newsapi.org/v2/top-headlines",
                params={"category": "business", "language": "en", "pageSize": 10},
                headers={"X-Api-Key": newsapi_key},
                timeout=10,
            )
            resp.raise_for_status()
            articles = resp.json().get("articles", [])
            return [a.get("title", "") for a in articles if a.get("title")]
        except Exception as exc:
            logger.warning(f"NewsAPI failed, falling back to Reuters RSS: {exc}")

    try:
        import feedparser  # noqa: PLC0415 — lazy import; feedparser may be unavailable
        feed = feedparser.parse("https://feeds.reuters.com/reuters/businessNews")
        return [e.get("title", "") for e in feed.entries[:10]]
    except Exception as exc:
        logger.warning(f"Reuters RSS failed: {exc}")
        return []


def _fetch_trends() -> dict:
    try:
        from pytrends.request import TrendReq
        terms = [
            "AI sales training",
            "language learning app",
            "automated trading",
            "EdTech",
            "dropshipping 2026",
        ]
        pytrends = TrendReq(hl="en-US", tz=360)
        pytrends.build_payload(terms, timeframe="today 1-m")
        df = pytrends.interest_over_time()
        if df is not None and not df.empty:
            return {col: int(df[col].iloc[-1]) for col in terms if col in df.columns}
    except Exception as exc:
        logger.warning(f"Pytrends failed: {exc}")
    return {}


def _fetch_stocks_status() -> dict:
    url = os.environ.get("SABLE_STOCKS_API_URL", "")
    secret = os.environ.get("SABLE_STOCKS_SECRET", "")
    if not url:
        return {}
    try:
        resp = httpx.get(
            f"{url}/api/status",
            headers={"X-Dashboard-Secret": secret},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning(f"Sable Stocks status fetch failed: {exc}")
        return {}


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text.strip())
    return json.loads(text)


class SableBusiness:
    def run(self) -> dict[str, Any]:
        start = time.time()

        headlines = _fetch_news()
        trends = _fetch_trends()
        stocks_status = _fetch_stocks_status()

        user_payload = {
            "headlines": headlines,
            "trends": trends,
            "sable_stocks_status": stocks_status,
        }

        result: dict[str, Any] = {
            "top_signals": [],
            "opportunity_of_the_day": {
                "name": "",
                "description": "",
                "revenue_potential": "",
                "startup_cost": "",
                "connection_to_ethan": "",
                "recommended_action": "",
            },
            "jt_alert": None,
            "watch_list": [],
            "spoken_summary": "",
        }

        status = "success"
        try:
            client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1500,
                system=_SYSTEM,
                messages=[{"role": "user", "content": json.dumps(user_payload)}],
            )
            parsed = _parse_json(message.content[0].text)
            # Enforce max 3 top_signals
            if "top_signals" in parsed:
                parsed["top_signals"] = parsed["top_signals"][:3]
            result.update(parsed)
            logger.info("Business agent completed")
        except Exception as exc:
            status = "error"
            result["spoken_summary"] = str(exc)
            logger.error(f"Business agent error: {exc}")

        duration = round(time.time() - start, 2)
        log_agent_run(
            "business", status,
            result.get("spoken_summary", "")[:300],
            json.dumps(result),
            duration,
        )
        return result
