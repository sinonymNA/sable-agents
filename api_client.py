import os

import httpx
from loguru import logger
from twilio.rest import Client as TwilioClient


def send_sms(to: str, body: str) -> bool:
    """Send an SMS via Twilio. Silent fail if credentials missing."""
    if not to:
        logger.warning("send_sms: no recipient number — skipping")
        return False
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    from_number = os.environ.get("TWILIO_FROM_NUMBER", "")
    if not all([account_sid, auth_token, from_number]):
        logger.warning("send_sms: Twilio credentials not configured — skipping")
        return False
    try:
        client = TwilioClient(account_sid, auth_token)
        msg = client.messages.create(body=body, from_=from_number, to=to)
        logger.info(f"SMS sent to {to}: {msg.sid}")
        return True
    except Exception as exc:
        logger.error(f"SMS send failed to {to}: {exc}")
        return False


def post_to_command(agent_name: str, payload: dict) -> bool:
    """POST agent result to Sable Command API. Silent fail if URL not set."""
    url = os.environ.get("SABLE_COMMAND_API_URL", "")
    if not url:
        logger.debug(f"SABLE_COMMAND_API_URL not set — skipping post for {agent_name}")
        return False
    try:
        headers = {"Content-Type": "application/json"}
        secret = os.environ.get("SABLE_COMMAND_SECRET", "")
        if secret:
            headers["X-Sable-Secret"] = secret
        resp = httpx.post(
            f"{url}/api/agent-result",
            json={"agent": agent_name, "payload": payload},
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        logger.info(f"Posted {agent_name} result to Sable Command")
        return True
    except Exception as exc:
        logger.error(f"Failed to post {agent_name} to Sable Command: {exc}")
        return False
