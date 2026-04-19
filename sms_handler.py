import json
import threading
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form
from fastapi.responses import Response
from loguru import logger
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import Gather, VoiceResponse

load_dotenv()

app = FastAPI(title="Sable SMS Handler")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "service": "sable-sms-handler"}


# ---------------------------------------------------------------------------
# SMS webhook
# ---------------------------------------------------------------------------

@app.post("/sms")
async def sms_webhook(
    Body: str = Form(default=""),
    From: str = Form(default=""),
    To: str = Form(default=""),
):
    cmd = Body.strip().upper()
    resp = MessagingResponse()

    if cmd in ("HELLO", "HI", "HEY", "START", "STATUS"):
        trade = _load_trade()
        resp.message(
            f"Sable is active.\n"
            f"Stocks gate: Day {trade['gate_day']}/{trade['gate_total']} | "
            f"P&L: ${float(trade['daily_pnl']):+,.2f} | "
            f"Status: {trade['status']}\n\n"
            f"Text HELP for commands."
        )

    elif cmd == "HELP":
        resp.message(
            "Sable commands:\n"
            "STATUS — system status\n"
            "TRADES — trade monitor snapshot\n"
            "CONTENT — generate content ideas now\n"
            "SALES — trigger sales brief now\n"
            "HELP — this list"
        )

    elif cmd == "TRADES":
        trade = _load_trade()
        resp.message(
            f"Sable Stocks\n"
            f"Gate: Day {trade['gate_day']}/{trade['gate_total']}\n"
            f"Daily P&L: ${float(trade['daily_pnl']):+,.2f}\n"
            f"Last trade: {trade['last_trade']}\n"
            f"Status: {trade['status']}"
        )

    elif cmd == "CONTENT":
        threading.Thread(target=_run_content_scout, daemon=True).start()
        resp.message("Running ContentScout now. Ideas on the way.")

    elif cmd == "SALES":
        threading.Thread(target=_run_sales_scout, daemon=True).start()
        resp.message("Running SalesScout now. Brief on the way to JT.")

    else:
        resp.message(
            "Sable received your message.\n"
            "Text HELP for available commands."
        )

    return Response(content=str(resp), media_type="application/xml")


# ---------------------------------------------------------------------------
# Voice webhooks
# ---------------------------------------------------------------------------

@app.post("/call")
async def call_webhook(
    CallSid: str = Form(default=""),
    From: str = Form(default=""),
):
    resp = VoiceResponse()
    gather = Gather(num_digits=1, action="/call-respond", timeout=10)
    gather.say(
        "You've reached Sable. "
        "Press 1 for a status update. "
        "Press 2 to run all agents now. "
        "Press 3 to hear the trade monitor status."
    )
    resp.append(gather)
    resp.say("No input received. Goodbye.")
    return Response(content=str(resp), media_type="application/xml")


@app.post("/call-respond")
async def call_respond(
    Digits: str = Form(default=""),
    CallSid: str = Form(default=""),
):
    resp = VoiceResponse()
    trade = _load_trade()

    if Digits == "1":
        resp.say(
            f"All Sable agents are active. "
            f"Trade gate is on day {trade['gate_day']} of {trade['gate_total']}. "
            f"Daily P and L is {trade['daily_pnl']} dollars. "
            f"Status is {trade['status']}. "
            f"Sales scout and content scout run daily. Finance agent runs weekly. Goodbye."
        )
    elif Digits == "2":
        threading.Thread(target=_run_all_agents, daemon=True).start()
        resp.say(
            "Running all agents now. You will receive text updates shortly. Goodbye."
        )
    elif Digits == "3":
        resp.say(
            f"Trade monitor status: "
            f"Gate day {trade['gate_day']} of {trade['gate_total']}. "
            f"Daily P and L: {trade['daily_pnl']} dollars. "
            f"Last trade: {trade['last_trade']}. "
            f"Status: {trade['status']}. Goodbye."
        )
    else:
        resp.say("Invalid input. Goodbye.")

    return Response(content=str(resp), media_type="application/xml")


# ---------------------------------------------------------------------------
# Sable Command API receiver
# ---------------------------------------------------------------------------

@app.post("/api/agent-result")
async def agent_result(request_body: dict):
    agent = request_body.get("agent", "unknown")
    logger.info(f"Agent result received: {agent}")
    return {"status": "received", "agent": agent}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_trade() -> dict:
    try:
        return json.loads(Path("data/trade_status.json").read_text())
    except Exception:
        return {"gate_day": 0, "gate_total": 20, "daily_pnl": 0, "last_trade": "none", "status": "unknown"}


def _run_content_scout():
    try:
        from agents.content_scout import ContentScout
        ContentScout().run()
    except Exception as exc:
        logger.error(f"ContentScout on-demand failed: {exc}")


def _run_sales_scout():
    try:
        from agents.sales_scout import SalesScout
        SalesScout().run()
    except Exception as exc:
        logger.error(f"SalesScout on-demand failed: {exc}")


def _run_all_agents():
    for fn in [_run_sales_scout, _run_content_scout]:
        try:
            fn()
        except Exception as exc:
            logger.error(f"On-demand agent failed: {exc}")
