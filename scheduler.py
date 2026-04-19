import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

scheduler = BlockingScheduler(timezone="America/New_York")


def run_sales_scout():
    logger.info("--- SalesScout starting ---")
    try:
        from agents.sales_scout import SalesScout
        SalesScout().run()
        logger.info("--- SalesScout complete ---")
    except Exception as exc:
        logger.error(f"SalesScout failed: {exc}")


def run_finance_agent():
    logger.info("--- FinanceAgent starting ---")
    try:
        from agents.finance_agent import FinanceAgent
        FinanceAgent().run()
        logger.info("--- FinanceAgent complete ---")
    except Exception as exc:
        logger.error(f"FinanceAgent failed: {exc}")


def run_trade_monitor():
    logger.info("--- TradeMonitor starting ---")
    try:
        from agents.trade_monitor import TradeMonitor
        TradeMonitor().run()
        logger.info("--- TradeMonitor complete ---")
    except Exception as exc:
        logger.error(f"TradeMonitor failed: {exc}")


def run_content_scout():
    logger.info("--- ContentScout starting ---")
    try:
        from agents.content_scout import ContentScout
        ContentScout().run()
        logger.info("--- ContentScout complete ---")
    except Exception as exc:
        logger.error(f"ContentScout failed: {exc}")


scheduler.add_job(
    run_sales_scout,
    CronTrigger(hour=7, minute=45, timezone="America/New_York"),
    id="sales_scout",
    replace_existing=True,
)

scheduler.add_job(
    run_finance_agent,
    CronTrigger(day_of_week="mon", hour=8, minute=0, timezone="America/New_York"),
    id="finance_agent",
    replace_existing=True,
)

scheduler.add_job(
    run_trade_monitor,
    IntervalTrigger(hours=1),
    id="trade_monitor",
    replace_existing=True,
)

scheduler.add_job(
    run_content_scout,
    CronTrigger(hour=6, minute=0, timezone="America/New_York"),
    id="content_scout",
    replace_existing=True,
)

if __name__ == "__main__":
    logger.info("Sable Scheduler starting")
    logger.info("  SalesScout    → daily 7:45 AM ET")
    logger.info("  FinanceAgent  → every Monday 8:00 AM ET")
    logger.info("  TradeMonitor  → every hour")
    logger.info("  ContentScout  → daily 6:00 AM ET")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
        sys.exit(0)
