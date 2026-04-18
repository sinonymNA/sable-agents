import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel

from db.models import (
    get_pending_approvals,
    get_todays_briefing,
    init_db,
    update_approval_status,
)
from scheduler.jobs import start_scheduler, stop_scheduler

os.makedirs("/tmp", exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Sable Agents", lifespan=lifespan)
app.mount("/audio", StaticFiles(directory="/tmp"), name="audio")


class ApprovalAction(BaseModel):
    status: str  # "approved" or "rejected"


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/briefing/today")
def briefing_today():
    briefing = get_todays_briefing()
    if not briefing:
        raise HTTPException(status_code=404, detail="No briefing found for today")
    return {
        "date": briefing.date,
        "business_section": briefing.business_section,
        "marketing_section": briefing.marketing_section,
        "finance_section": briefing.finance_section,
        "guide_section": briefing.guide_section,
        "full_text": briefing.full_text,
        "audio_url": briefing.audio_url,
        "call_sid": briefing.call_sid,
        "created_at": briefing.created_at.isoformat() if briefing.created_at else None,
    }


@app.get("/api/approvals/pending")
def pending_approvals():
    approvals = get_pending_approvals()
    return [
        {
            "id": a.id,
            "agent": a.agent,
            "content_type": a.content_type,
            "content_text": a.content_text,
            "platform": a.platform,
            "requested_at": a.requested_at.isoformat() if a.requested_at else None,
        }
        for a in approvals
    ]


@app.post("/api/approvals/{approval_id}")
def decide_approval(approval_id: int, action: ApprovalAction):
    if action.status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="status must be 'approved' or 'rejected'")
    update_approval_status(approval_id, action.status)
    return {"id": approval_id, "status": action.status}


@app.post("/api/run-now")
def run_now():
    import threading
    from scheduler.jobs import run_agents_job
    t = threading.Thread(target=run_agents_job, daemon=True)
    t.start()
    return {"status": "started", "message": "Agent pipeline running. You'll get an SMS when done."}


@app.post("/api/sms/webhook")
async def sms_webhook(
    Body: str = Form(default=""),
    From: str = Form(default=""),
    To: str = Form(default=""),
):
    from sms.handler import handle_incoming
    reply = await handle_incoming(Body, From)
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response><Message>{reply}</Message></Response>"""
    return Response(content=twiml, media_type="application/xml")
