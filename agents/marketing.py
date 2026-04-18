import json
import os
import re
import time
from typing import Any

import anthropic
from loguru import logger

from db.models import ContentQueue, SessionLocal, get_pending_approvals, log_agent_run, log_approval

_SYSTEM = """You are Sable Marketing, the content and marketing agent for Sable.

Ethan's voice: direct, warm, precise, intellectually serious. AP History teacher who builds \
AI systems. Writes under pen name Micah Eres. No hype, no buzzwords. Sounds like a smart \
22-year-old who built something real.

Active platforms:
- Substack (Micah Eres): narrative, reflective, personal
- X/Twitter: direct insights, threads
- TikTok: educational hooks, behind-the-scenes builds

Products to market:
- FreshUp AI (JT sells, Ethan brands)
- Sable Stocks (document the build)
- Micah Eres writing brand

Rules:
- Never post anything that feels fake
- Never use: game changer, revolutionize, disrupting, transformative
- Always connect to something true in Ethan's actual life
- TikTok hooks must be under 8 words

Respond ONLY in this JSON, no preamble, no markdown:
{
  "content_pieces": [{
    "platform": str,
    "type": str,
    "content": str,
    "hook": str,
    "why_this_works": str,
    "ready_to_approve": bool
  }],
  "todays_priority": str,
  "performance_note": str,
  "spoken_summary": str
}"""


def _get_recent_content() -> list[dict]:
    try:
        with SessionLocal() as s:
            rows = (
                s.query(ContentQueue)
                .order_by(ContentQueue.created_at.desc())
                .limit(10)
                .all()
            )
            return [
                {
                    "platform": r.platform,
                    "content_text": (r.content_text or "")[:200],
                    "status": r.status,
                }
                for r in rows
            ]
    except Exception as exc:
        logger.warning(f"Content queue query failed: {exc}")
        return []


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text.strip())
    return json.loads(text)


class SableMarketing:
    def run(self, business_output: dict) -> dict[str, Any]:
        start = time.time()

        pending_approvals = get_pending_approvals()
        recent_content = _get_recent_content()

        user_payload = {
            "business_output": business_output,
            "pending_approval_count": len(pending_approvals),
            "recent_content": recent_content,
        }

        result: dict[str, Any] = {
            "content_pieces": [],
            "todays_priority": "",
            "performance_note": "",
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
            # Enforce max 3 content pieces
            if "content_pieces" in parsed:
                parsed["content_pieces"] = parsed["content_pieces"][:3]
            result.update(parsed)

            for piece in result.get("content_pieces", []):
                if piece.get("ready_to_approve"):
                    log_approval(
                        agent="marketing",
                        content_type=piece.get("type", "post"),
                        content_text=piece.get("content", ""),
                        platform=piece.get("platform", ""),
                    )

            logger.info("Marketing agent completed")
        except Exception as exc:
            status = "error"
            result["spoken_summary"] = str(exc)
            logger.error(f"Marketing agent error: {exc}")

        duration = round(time.time() - start, 2)
        log_agent_run(
            "marketing", status,
            result.get("spoken_summary", "")[:300],
            json.dumps(result),
            duration,
        )
        return result
