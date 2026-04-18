import json
import os
import re
import time
from typing import Any

import anthropic
from loguru import logger

from db.models import log_agent_run

_SYSTEM = """You are Sable Guide, the chief of staff for Sable. The other three agents report \
to you. You read everything they found, identify conflicts, and give Ethan one clear directive \
for the week.

Ethan's constraints:
- Teaches Monday through Friday
- Acts only during prep periods, after school, and weekends
- JT is his only sales resource for FreshUp
- 20-day paper trading gate cannot be rushed
- High capability, limited time

Never give more than one primary directive per day. Resolve conflicts between what Business \
wants and what Finance says is realistic. Protect Ethan's time ruthlessly.

Respond ONLY in this JSON, no preamble, no markdown:
{
  "weekly_directive": str,
  "why_this_over_everything_else": str,
  "what_to_stop": str,
  "conflicts_resolved": [str],
  "for_jt": str,
  "for_alex": str,
  "spoken_summary": str
}"""


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text.strip())
    return json.loads(text)


class SableGuide:
    def run(
        self,
        finance_out: dict,
        business_out: dict,
        marketing_out: dict,
    ) -> dict[str, Any]:
        start = time.time()

        user_payload = {
            "finance": finance_out,
            "business": business_out,
            "marketing": marketing_out,
        }

        result: dict[str, Any] = {
            "weekly_directive": "",
            "why_this_over_everything_else": "",
            "what_to_stop": "",
            "conflicts_resolved": [],
            "for_jt": None,
            "for_alex": None,
            "spoken_summary": "",
        }

        status = "success"
        try:
            client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=_SYSTEM,
                messages=[{"role": "user", "content": json.dumps(user_payload)}],
            )
            parsed = _parse_json(message.content[0].text)
            result.update(parsed)
            logger.info("Guide agent completed")
        except Exception as exc:
            status = "error"
            result["spoken_summary"] = str(exc)
            logger.error(f"Guide agent error: {exc}")

        duration = round(time.time() - start, 2)
        log_agent_run(
            "guide", status,
            result.get("spoken_summary", "")[:300],
            json.dumps(result),
            duration,
        )
        return result
