import os
import threading

from loguru import logger
from twilio.rest import Client

from db.models import (
    get_pending_approvals,
    get_todays_briefing,
    log_sms,
    update_approval_status,
)

# ---------------------------------------------------------------------------
# Outbound helpers
# ---------------------------------------------------------------------------

def send_sms(body: str) -> None:
    """Send a proactive SMS to the operator."""
    to = os.environ.get("OPERATOR_PHONE_NUMBER", "")
    from_ = os.environ.get("TWILIO_FROM_NUMBER", "")
    if not to or not from_:
        logger.warning("Twilio phone numbers not configured — SMS not sent")
        return
    try:
        client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
        msg = client.messages.create(body=body, from_=from_, to=to)
        log_sms("out", body, from_, to)
        logger.info(f"SMS sent: {msg.sid}")
    except Exception as exc:
        logger.error(f"SMS send failed: {exc}")


def notify_new_approval(approval) -> None:
    """Proactively text operator when a content piece needs approval."""
    preview = (approval.content_text or "")[:220]
    body = (
        f"[{(approval.agent or '').upper()} · {approval.platform}] New content:\n\n"
        f"{preview}\n\n"
        f"Reply APPROVE {approval.id} or REJECT {approval.id}"
    )
    send_sms(body)


def notify_briefing_complete(script: str, audio_url: str | None) -> None:
    """Text operator after the morning agent run finishes."""
    audio_line = "Audio ready." if audio_url else "No audio (check ElevenLabs config)."
    preview = (script or "")[:120]
    body = (
        f"Morning briefing done. {audio_line}\n\n"
        f'"{preview}..."\n\n'
        f"Text HELLO for status · APPROVALS to review content"
    )
    send_sms(body)


# ---------------------------------------------------------------------------
# Inbound handler (called from SMS webhook)
# ---------------------------------------------------------------------------

async def handle_incoming(body: str, from_number: str) -> str:
    operator = os.environ.get("OPERATOR_PHONE_NUMBER", "")
    log_sms("in", body, from_number, operator)

    raw = body.strip()
    cmd = raw.upper()
    parts = cmd.split()
    first = parts[0] if parts else ""

    if first in ("HELLO", "HI", "HEY", "START"):
        reply = _hello()
    elif first == "STATUS":
        reply = _status()
    elif first == "APPROVALS":
        reply = _list_approvals()
    elif first == "APPROVE":
        reply = _approve(parts[1] if len(parts) > 1 else None)
    elif first == "REJECT":
        reply = _reject(parts[1] if len(parts) > 1 else None)
    elif first == "RUN":
        reply = _run()
    elif first == "HELP":
        reply = _help()
    else:
        reply = (
            "Hey, I'm Sable. I don't understand that yet.\n\n"
            "Try: HELLO · STATUS · APPROVALS · APPROVE <id> · REJECT <id> · RUN · HELP"
        )

    _send_reply(reply, from_number)
    return reply


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _hello() -> str:
    briefing = get_todays_briefing()
    pending = get_pending_approvals()

    if briefing:
        audio = "Audio is ready." if briefing.audio_url else "No audio yet."
        call = f"Call placed ({briefing.call_sid[:8]}...)." if briefing.call_sid else "Call not placed yet."
        briefing_line = f"Today's briefing is ready. {audio} {call}"
    else:
        briefing_line = "No briefing yet today."

    if pending:
        pending_line = f"{len(pending)} content piece(s) waiting for your approval."
    else:
        pending_line = "No pending approvals."

    return (
        f"Hey. {briefing_line}\n\n"
        f"{pending_line}\n\n"
        f"APPROVALS to review · STATUS for details · RUN to trigger agents now"
    )


def _status() -> str:
    briefing = get_todays_briefing()
    pending = get_pending_approvals()

    if not briefing:
        return (
            f"No briefing for today yet.\n"
            f"{len(pending)} pending approval(s).\n\n"
            f"Text RUN to trigger agents now."
        )

    audio = "Ready" if briefing.audio_url else "Not generated"
    call = briefing.call_sid or "Not placed"
    return (
        f"Briefing: {briefing.date}\n"
        f"Audio: {audio}\n"
        f"Call SID: {call}\n"
        f"Pending approvals: {len(pending)}"
    )


def _list_approvals() -> str:
    pending = get_pending_approvals()
    if not pending:
        return "No pending approvals right now."
    lines = []
    for a in pending:
        preview = (a.content_text or "")[:100]
        lines.append(f"[{a.id}] {a.platform} ({a.agent})\n{preview}...")
    return "Pending approvals:\n\n" + "\n\n".join(lines) + "\n\nReply APPROVE <id> or REJECT <id>"


def _approve(id_str: str | None) -> str:
    pending = get_pending_approvals()
    if not pending:
        return "No pending approvals."

    if id_str is None:
        if len(pending) == 1:
            a = pending[0]
            update_approval_status(a.id, "approved")
            return f"Approved [{a.id}] {a.platform} post."
        ids = ", ".join(str(a.id) for a in pending)
        return f"{len(pending)} approvals pending. Which one? Reply APPROVE <id>\nIDs: {ids}"

    try:
        update_approval_status(int(id_str), "approved")
        return f"Approved [{id_str}]. Done."
    except ValueError:
        return "Usage: APPROVE <id>"


def _reject(id_str: str | None) -> str:
    pending = get_pending_approvals()
    if not pending:
        return "No pending approvals."

    if id_str is None:
        if len(pending) == 1:
            a = pending[0]
            update_approval_status(a.id, "rejected")
            return f"Rejected [{a.id}] {a.platform} post."
        ids = ", ".join(str(a.id) for a in pending)
        return f"{len(pending)} approvals pending. Which one? Reply REJECT <id>\nIDs: {ids}"

    try:
        update_approval_status(int(id_str), "rejected")
        return f"Rejected [{id_str}]."
    except ValueError:
        return "Usage: REJECT <id>"


def _run() -> str:
    from scheduler.jobs import run_agents_job
    t = threading.Thread(target=run_agents_job, daemon=True)
    t.start()
    return "Running agents now. I'll text you when the briefing is ready."


def _help() -> str:
    return (
        "Sable commands:\n\n"
        "HELLO — morning status\n"
        "STATUS — briefing + call details\n"
        "APPROVALS — list content waiting\n"
        "APPROVE <id> — approve a post\n"
        "REJECT <id> — reject a post\n"
        "RUN — trigger agents now\n"
        "HELP — this list"
    )


def _send_reply(body: str, to_number: str) -> None:
    try:
        client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
        msg = client.messages.create(
            body=body,
            from_=os.environ["TWILIO_FROM_NUMBER"],
            to=to_number,
        )
        log_sms("out", body, os.environ["TWILIO_FROM_NUMBER"], to_number)
        logger.info(f"SMS reply sent: {msg.sid}")
    except Exception as exc:
        logger.error(f"SMS reply failed: {exc}")
