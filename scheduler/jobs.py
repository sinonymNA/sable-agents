import asyncio
import os
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

scheduler = AsyncIOScheduler(timezone="America/New_York")


async def run_agents_job() -> None:
    """Run all four agents and save briefing sections to DB."""
    logger.info("Starting agent run job")
    from agents import business, finance, guide, marketing
    from briefing.synthesizer import synthesize
    from db.models import save_briefing

    results = await asyncio.gather(
        business.run(),
        marketing.run(),
        finance.run(),
        guide.run(),
        return_exceptions=True,
    )

    biz, mkt, fin, gui = [
        r if isinstance(r, dict) else {"summary": str(r), "raw_output": str(r), "status": "error"}
        for r in results
    ]

    script = await synthesize(biz, mkt, fin, gui)
    today = date.today().isoformat()
    save_briefing(
        date_str=today,
        business=biz.get("raw_output", ""),
        marketing=mkt.get("raw_output", ""),
        finance=fin.get("raw_output", ""),
        guide=gui.get("raw_output", ""),
        full_text=script,
    )
    logger.info(f"Agent run job complete for {today}")


async def send_briefing_job() -> None:
    """Generate audio and place the morning call."""
    logger.info("Starting briefing call job")
    from briefing.call import place_call
    from briefing.voice import generate_audio
    from db.models import get_todays_briefing, update_briefing

    briefing = get_todays_briefing()
    if not briefing or not briefing.full_text:
        logger.warning("No briefing found for today — skipping call")
        return

    voice_id = os.environ.get("ELEVENLABS_VOICE_BUSINESS", "")
    audio_path = await generate_audio(briefing.full_text, voice_id)

    # In production, upload audio_path to a public URL (e.g. S3/R2) before calling.
    # For now we pass the path directly — replace with your upload logic.
    audio_url = audio_path
    update_briefing(briefing.date, audio_url=audio_url)

    place_call(audio_url)
    logger.info("Briefing call job complete")


def _parse_time(env_var: str, default: str) -> tuple[int, int]:
    raw = os.environ.get(env_var, default)
    h, m = raw.split(":")
    return int(h), int(m)


def start_scheduler() -> None:
    agent_h, agent_m = _parse_time("AGENT_RUN_TIME", "05:00")
    call_h, call_m = _parse_time("BRIEFING_CALL_TIME", "06:00")

    scheduler.add_job(
        run_agents_job,
        CronTrigger(hour=agent_h, minute=agent_m, timezone="America/New_York"),
        id="run_agents",
        replace_existing=True,
    )
    scheduler.add_job(
        send_briefing_job,
        CronTrigger(hour=call_h, minute=call_m, timezone="America/New_York"),
        id="send_briefing",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"Scheduler started — agents at {agent_h:02d}:{agent_m:02d} ET, call at {call_h:02d}:{call_m:02d} ET")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
