import json
import os
import re
import time

import httpx
from anthropic import Anthropic
from loguru import logger

from api_client import post_to_command, send_sms

_MODEL = "claude-sonnet-4-6"
_BUFFER_API_URL = "https://api.bufferapp.com/1/updates/create.json"

_SYSTEM = """You are a social media copywriter for a dropshipping brand called Sable Store.
You write platform-native posts that sell products without feeling like ads.

Platform rules:
- instagram: 150-220 char caption + 15-20 relevant hashtags on a new line. First line must hook the scroll.
- twitter: under 240 chars. Punchy, conversational. Max 2 hashtags. Sounds like a real person.
- facebook: 200-280 chars. Benefit-focused. Ends with a question to drive comments.
- tiktok: NOT a caption. A spoken video script: one hook line (under 7 words) + 3 bullet talking points.

Voice: direct, not hype. Sounds like someone who found something useful.
Never use: "game changer", "life changing", "you need this", "must have", "obsessed".

schedule_offset_hours values: instagram=0, twitter=24, facebook=48, tiktok=0

Respond ONLY in this JSON, no preamble, no markdown fences:
{
  "posts": [
    {
      "platform": "instagram",
      "content": "string",
      "schedule_offset_hours": 0
    },
    {
      "platform": "twitter",
      "content": "string",
      "schedule_offset_hours": 24
    },
    {
      "platform": "facebook",
      "content": "string",
      "schedule_offset_hours": 48
    },
    {
      "platform": "tiktok",
      "content": "string",
      "schedule_offset_hours": 0
    }
  ],
  "campaign_summary": "string"
}"""


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text.strip())
    return json.loads(text)


def _get_buffer_profile_ids() -> dict[str, str]:
    """Parse BUFFER_PROFILE_IDS=instagram:ID1,twitter:ID2,facebook:ID3"""
    raw = os.environ.get("BUFFER_PROFILE_IDS", "")
    profiles: dict[str, str] = {}
    for pair in raw.split(","):
        if ":" in pair:
            platform, pid = pair.strip().split(":", 1)
            profiles[platform.strip().lower()] = pid.strip()
    return profiles


def _schedule_to_buffer(content: str, profile_id: str, scheduled_at: int) -> dict:
    token = os.environ.get("BUFFER_ACCESS_TOKEN", "")
    resp = httpx.post(
        _BUFFER_API_URL,
        data={
            "profile_ids[]": profile_id,
            "text": content,
            "scheduled_at": str(scheduled_at),
            "now": "false",
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


class BrandingAgent:
    def run(
        self,
        product_name: str,
        shopify_url: str | None = None,
        opportunity: dict | None = None,
    ) -> dict:
        logger.info(f"--- BrandingAgent starting for: {product_name} ---")
        result: dict = {
            "product_name": product_name,
            "posts_generated": 0,
            "posts_scheduled": 0,
            "buffer_results": [],
            "posts": [],
            "campaign_summary": "",
            "status": "error",
        }

        try:
            user_payload = {
                "product_name": product_name,
                "shopify_url": shopify_url or "",
                "opportunity_context": opportunity or {},
            }
            client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
            message = client.messages.create(
                model=_MODEL,
                max_tokens=1500,
                system=_SYSTEM,
                messages=[{"role": "user", "content": json.dumps(user_payload)}],
            )
            claude_result = _parse_json(message.content[0].text)
            posts = claude_result.get("posts", [])[:4]
            result["posts"] = posts
            result["posts_generated"] = len(posts)
            result["campaign_summary"] = claude_result.get("campaign_summary", "")

        except Exception as exc:
            logger.error(f"BrandingAgent Claude call failed: {exc}")
            body = f"BrandingAgent couldn't generate posts for '{product_name}': {exc}\n— Sable"
            send_sms(os.environ.get("ETHAN_PHONE_NUMBER", ""), body)
            post_to_command("branding_agent", result)
            return result

        profile_ids = _get_buffer_profile_ids()
        scheduled_count = 0
        failed_platforms: list[str] = []
        now_ts = int(time.time())

        for post in posts:
            platform = post.get("platform", "")
            if platform == "tiktok":
                continue

            profile_id = profile_ids.get(platform)
            if not profile_id:
                logger.warning(f"No Buffer profile ID for {platform} — skipping")
                continue

            scheduled_at = now_ts + (post.get("schedule_offset_hours", 0) * 3600)
            try:
                buffer_resp = _schedule_to_buffer(post["content"], profile_id, scheduled_at)
                result["buffer_results"].append({"platform": platform, "response": buffer_resp})
                scheduled_count += 1
            except Exception as exc:
                logger.error(f"Buffer schedule failed for {platform}: {exc}")
                failed_platforms.append(platform)

        result["posts_scheduled"] = scheduled_count
        result["status"] = "success" if not failed_platforms else "partial"

        tiktok_post = next((p for p in posts if p["platform"] == "tiktok"), None)
        tiktok_line = "\nTikTok script saved — post manually." if tiktok_post else ""

        platforms_ok = [p["platform"].title() for p in posts if p["platform"] != "tiktok" and p["platform"] not in failed_platforms]
        failed_line = f"\nFailed: {', '.join(failed_platforms)}" if failed_platforms else ""

        body = (
            f"Branding done for {product_name}:\n"
            f"{scheduled_count} posts scheduled → {', '.join(platforms_ok)}"
            f"{failed_line}"
            f"{tiktok_line}\n— Sable"
        )

        send_sms(os.environ.get("ETHAN_PHONE_NUMBER", ""), body)
        post_to_command("branding_agent", result)
        logger.info("--- BrandingAgent complete ---")
        return result
