import os
from datetime import date

from loguru import logger
from twilio.rest import Client

from db.models import update_briefing


def place_call(audio_url: str, to_number: str | None = None) -> str:
    """Place a Twilio voice call that plays audio_url. Returns call SID."""
    account_sid = os.environ["TWILIO_ACCOUNT_SID"]
    auth_token = os.environ["TWILIO_AUTH_TOKEN"]
    from_number = os.environ["TWILIO_FROM_NUMBER"]
    to_number = to_number or os.environ["OPERATOR_PHONE_NUMBER"]

    client = Client(account_sid, auth_token)

    twiml = f'<Response><Play>{audio_url}</Play></Response>'

    call = client.calls.create(
        twiml=twiml,
        to=to_number,
        from_=from_number,
    )

    logger.info(f"Call placed to {to_number}, SID={call.sid}")
    update_briefing(date.today().isoformat(), call_sid=call.sid)
    return call.sid
