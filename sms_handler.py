import json
import threading
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form
from fastapi.responses import Response
from loguru import logger
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import Gather, VoiceResponse

from voice_agent import clear_session, marcus_respond

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
    cmd = Body.strip()
    cmd_upper = cmd.upper()
    first_word = cmd_upper.split()[0] if cmd_upper.split() else ""
    rest = cmd[len(first_word):].strip()   # preserves original casing for product names

    resp = MessagingResponse()

    if cmd_upper in ("HELLO", "HI", "HEY", "START", "STATUS"):
        trade = _load_trade()
        resp.message(
            f"Sable is active.\n"
            f"Stocks gate: Day {trade['gate_day']}/{trade['gate_total']} | "
            f"P&L: ${float(trade['daily_pnl']):+,.2f} | "
            f"Status: {trade['status']}\n\n"
            f"Text HELP for commands."
        )

    elif cmd_upper == "HELP":
        resp.message(
            "Sable commands:\n"
            "STATUS — system status\n"
            "TRADES — trade monitor snapshot\n"
            "CONTENT — generate content ideas now\n"
            "SALES — trigger sales brief now\n"
            "TRENDS — scan Google Trends for dropshipping products\n"
            "TRENDS [product] — scan for a specific product\n"
            "SHOP [product] — create Shopify listing\n"
            "BRAND [product] — generate & schedule social posts\n"
            "HELP — this list"
        )

    elif cmd_upper == "TRADES":
        trade = _load_trade()
        resp.message(
            f"Sable Stocks\n"
            f"Gate: Day {trade['gate_day']}/{trade['gate_total']}\n"
            f"Daily P&L: ${float(trade['daily_pnl']):+,.2f}\n"
            f"Last trade: {trade['last_trade']}\n"
            f"Status: {trade['status']}"
        )

    elif cmd_upper == "CONTENT":
        threading.Thread(target=_run_content_scout, daemon=True).start()
        resp.message("Running ContentScout now. Ideas on the way.")

    elif cmd_upper == "SALES":
        threading.Thread(target=_run_sales_scout, daemon=True).start()
        resp.message("Running SalesScout now. Brief on the way to JT.")

    elif first_word == "TRENDS":
        hint = rest if rest else None
        threading.Thread(target=_run_trends_scout, args=(hint,), daemon=True).start()
        if hint:
            resp.message(f"Scanning trends for '{hint}'. Results on the way.")
        else:
            resp.message("Scanning all 6 categories. Top 3 opportunities incoming.")

    elif first_word == "SHOP":
        if not rest:
            resp.message("Tell me the product. Example:\nSHOP electric lash curler")
        else:
            threading.Thread(target=_run_shopify_agent, args=(rest,), daemon=True).start()
            resp.message(f"Creating Shopify draft listing for '{rest}'. Admin link incoming.")

    elif first_word == "BRAND":
        if not rest:
            resp.message("Tell me the product. Example:\nBRAND foam roller set")
        else:
            threading.Thread(target=_run_branding_agent, args=(rest,), daemon=True).start()
            resp.message(f"Generating social posts for '{rest}'. Scheduling to Buffer now.")

    else:
        resp.message(
            "Sable received your message.\n"
            "Text HELP for available commands."
        )

    return Response(content=str(resp), media_type="application/xml")


# ---------------------------------------------------------------------------
# Voice webhooks — conversational Marcus COS
# ---------------------------------------------------------------------------

@app.post("/call")
async def call_webhook(
    CallSid: str = Form(default=""),
    From: str = Form(default=""),
):
    resp = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/voice-respond",
        speechTimeout="auto",
        timeout=8,
    )
    gather.say("Marcus here. What's on your agenda?", voice="Polly.Matthew")
    resp.append(gather)
    resp.say("I didn't catch that. Call back when you're ready.", voice="Polly.Matthew")
    return Response(content=str(resp), media_type="application/xml")


@app.post("/voice-respond")
async def voice_respond(
    SpeechResult: str = Form(default=""),
    CallSid: str = Form(default=""),
):
    if not SpeechResult.strip():
        resp = VoiceResponse()
        gather = Gather(input="speech", action="/voice-respond", speechTimeout="auto", timeout=8)
        gather.say("Sorry, I didn't catch that. Go ahead.", voice="Polly.Matthew")
        resp.append(gather)
        resp.say("Talk soon.", voice="Polly.Matthew")
        return Response(content=str(resp), media_type="application/xml")

    segments, should_end = marcus_respond(CallSid, SpeechResult)

    resp = VoiceResponse()

    if should_end:
        for seg in segments:
            resp.say(seg["text"], voice=seg["voice"])
        clear_session(CallSid)
        return Response(content=str(resp), media_type="application/xml")

    gather = Gather(input="speech", action="/voice-respond", speechTimeout="auto", timeout=8)
    for i, seg in enumerate(segments):
        gather.say(seg["text"], voice=seg["voice"])
        if i < len(segments) - 1:
            gather.pause(length=1)
    resp.append(gather)
    resp.say("Talk soon.", voice="Polly.Matthew")
    return Response(content=str(resp), media_type="application/xml")


@app.post("/call-status")
async def call_status(
    CallSid: str = Form(default=""),
    CallStatus: str = Form(default=""),
):
    if CallStatus in ("completed", "busy", "failed", "no-answer", "canceled"):
        clear_session(CallSid)
        logger.info(f"Call {CallSid} ended ({CallStatus}) — session cleared")
    return Response(content="", status_code=204)


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


def _run_trends_scout(product_hint: str | None = None):
    try:
        from agents.trends_scout import TrendsScout
        TrendsScout().run(product_hint=product_hint)
    except Exception as exc:
        logger.error(f"TrendsScout on-demand failed: {exc}")


def _run_shopify_agent(product_name: str):
    try:
        from agents.shopify_agent import ShopifyAgent
        ShopifyAgent().run(product_name=product_name)
    except Exception as exc:
        logger.error(f"ShopifyAgent on-demand failed: {exc}")


def _run_branding_agent(product_name: str):
    try:
        from agents.branding_agent import BrandingAgent
        BrandingAgent().run(product_name=product_name)
    except Exception as exc:
        logger.error(f"BrandingAgent on-demand failed: {exc}")
