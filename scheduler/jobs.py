import os
import time
import traceback
from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

scheduler = BackgroundScheduler(timezone="America/New_York")


def run_agents_job():
    """Run all four agents, synthesize, generate audio, and save to DB."""
    logger.info("Starting agent run job")
    start = time.time()

    try:
        from agents.finance import SableFinance
        finance_out = SableFinance().run()
        logger.info("Finance agent done")

        from agents.business import SableBusiness
        business_out = SableBusiness().run()
        logger.info("Business agent done")

        from agents.marketing import SableMarketing
        marketing_out = SableMarketing().run(business_out)
        logger.info("Marketing agent done")

        from agents.guide import SableGuide
        guide_out = SableGuide().run(finance_out, business_out, marketing_out)
        logger.info("Guide agent done")

        from briefing.synthesizer import synthesize
        script = synthesize(finance_out, business_out, marketing_out, guide_out)
        logger.info("Briefing synthesized")

        from briefing.voice import convert_to_audio
        today_str = str(date.today())
        audio_url = convert_to_audio(script, today_str)
        logger.info(f"Audio URL: {audio_url}")

        from db.models import save_briefing, update_briefing
        save_briefing(
            date_str=today_str,
            business=business_out.get("spoken_summary", ""),
            marketing=marketing_out.get("spoken_summary", ""),
            finance=finance_out.get("spoken_summary", ""),
            guide=guide_out.get("spoken_summary", ""),
            full_text=script,
        )
        if audio_url:
            update_briefing(today_str, audio_url=audio_url)

        elapsed = time.time() - start
        print(f"Agents complete in {elapsed:.1f}s")
        print(f"Audio URL: {audio_url}")
        logger.info(f"Agent run job complete in {elapsed:.1f}s")
        return script, audio_url

    except Exception as e:
        print(f"Agent run failed: {e}")
        traceback.print_exc()
        logger.error(f"Agent run job failed: {e}")
        return None, None


def send_briefing_job():
    """Place morning call using audio URL saved by run_agents_job."""
    logger.info("Starting briefing call job")
    from briefing.call import place_call
    from db.models import get_todays_briefing

    briefing = get_todays_briefing()
    if not briefing or not briefing.audio_url:
        logger.warning("No briefing audio found for today — skipping call")
        return

    place_call(briefing.audio_url)
    logger.info("Briefing call placed")


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
    logger.info(
        f"Scheduler started — agents at {agent_h:02d}:{agent_m:02d} ET, "
        f"call at {call_h:02d}:{call_m:02d} ET"
    )


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
