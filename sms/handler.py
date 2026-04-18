import os

from loguru import logger
from twilio.rest import Client

from db.models import get_pending_approvals, get_todays_briefing, log_sms, update_approval_status

_HELP = "Commands: STATUS | APPROVE <id> | REJECT <id> | APPROVALS"


async def handle_incoming(body: str, from_number: str) -> str:
    operator = os.environ.get("OPERATOR_PHONE_NUMBER", "")
    log_sms("in", body, from_number, operator)

    cmd = body.strip().upper()
    parts = cmd.split()

    if cmd == "STATUS":
        briefing = get_todays_briefing()
        if briefing:
            reply = f"Briefing ready. Audio: {'yes' if briefing.audio_url else 'no'}. Call SID: {briefing.call_sid or 'none'}."
        else:
            reply = "No briefing generated yet today."

    elif cmd == "APPROVALS":
        pending = get_pending_approvals()
        if pending:
            lines = [f"[{a.id}] {a.agent}/{a.platform}: {(a.content_text or '')[:60]}..." for a in pending]
            reply = "\n".join(lines)
        else:
            reply = "No pending approvals."

    elif len(parts) == 2 and parts[0] == "APPROVE":
        try:
            approval_id = int(parts[1])
            update_approval_status(approval_id, "approved")
            reply = f"Approval {approval_id} approved."
        except ValueError:
            reply = "Usage: APPROVE <id>"

    elif len(parts) == 2 and parts[0] == "REJECT":
        try:
            approval_id = int(parts[1])
            update_approval_status(approval_id, "rejected")
            reply = f"Approval {approval_id} rejected."
        except ValueError:
            reply = "Usage: REJECT <id>"

    else:
        reply = _HELP

    _send_sms(reply, from_number)
    return reply


def _send_sms(body: str, to_number: str) -> None:
    try:
        client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
        msg = client.messages.create(
            body=body,
            from_=os.environ["TWILIO_FROM_NUMBER"],
            to=to_number,
        )
        operator = os.environ.get("OPERATOR_PHONE_NUMBER", "")
        log_sms("out", body, os.environ["TWILIO_FROM_NUMBER"], to_number)
        logger.info(f"SMS sent to {to_number}: {msg.sid}")
    except Exception as exc:
        logger.error(f"SMS send failed: {exc}")
