import os

from anthropic import Anthropic
from loguru import logger

from api_client import post_to_command, send_sms

_SYSTEM = """You are Sable Brain generating content ideas for Micah Eres.

Micah Eres is a pen name for writing about building real autonomous income systems.
Themes: AI, personal finance, education, autonomous income.
Voice: Direct, intellectually serious, grounded in real experience. No hype, no buzzwords,
no get-rich-quick framing. Sounds like someone who actually built the systems they write about.
Audience: People who want to build real financial independence through systems, not luck.

Generate exactly 3 Substack article ideas. For each:
- Title (punchy, specific, no clickbait)
- Hook (one sentence — what the reader learns or gets)
- Why now (one sentence — why this matters this week)

Format:
1. [Title]
Hook: [hook]
Why now: [why now]

2. [Title]
...

This will be sent as a text message. Keep each idea tight."""


class ContentScout:
    def run(self) -> str:
        logger.info("ContentScout starting")
        try:
            client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
            message = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=512,
                system=_SYSTEM,
                messages=[{
                    "role": "user",
                    "content": "Generate 3 Substack article ideas for Micah Eres for today.",
                }],
            )
            ideas = message.content[0].text.strip()
        except Exception as exc:
            logger.error(f"ContentScout Claude call failed: {exc}")
            ideas = "ContentScout unavailable today. Check ANTHROPIC_API_KEY."

        body = f"Content Ideas — Micah Eres:\n\n{ideas}\n\n— Sable"
        send_sms(os.environ.get("ETHAN_PHONE_NUMBER", ""), body)
        post_to_command("content_scout", {"ideas": ideas, "status": "sent"})
        logger.info("ContentScout complete")
        return ideas
