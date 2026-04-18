import os
from datetime import date, datetime
from typing import Optional

from dotenv import load_dotenv
from loguru import logger
from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, create_engine, text,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()

_raw_url = os.getenv("DATABASE_URL", "")

if _raw_url:
    # Railway sometimes provides postgres:// which SQLAlchemy 2.x requires as postgresql://
    if _raw_url.startswith("postgres://"):
        _raw_url = _raw_url.replace("postgres://", "postgresql://", 1)
    _connect_args = {"sslmode": "require"} if "postgresql" in _raw_url else {}
    engine = create_engine(_raw_url, connect_args=_connect_args, pool_pre_ping=True)
else:
    engine = create_engine("sqlite:///sable.db", connect_args={"check_same_thread": False})
    logger.warning("DATABASE_URL not set — using local SQLite (sable.db)")

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id = Column(Integer, primary_key=True)
    agent_name = Column(String(64), nullable=False)
    run_date = Column(String(10), nullable=False)  # YYYY-MM-DD
    status = Column(String(16), nullable=False, default="pending")
    output_summary = Column(Text)
    raw_output = Column(Text)
    duration_seconds = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class Briefing(Base):
    __tablename__ = "briefings"
    id = Column(Integer, primary_key=True)
    date = Column(String(10), nullable=False, unique=True)
    business_section = Column(Text)
    marketing_section = Column(Text)
    finance_section = Column(Text)
    guide_section = Column(Text)
    full_text = Column(Text)
    script = Column(Text)
    audio_url = Column(String(512))
    call_sid = Column(String(64))
    created_at = Column(DateTime, default=datetime.utcnow)


class Decision(Base):
    __tablename__ = "decisions"
    id = Column(Integer, primary_key=True)
    briefing_id = Column(Integer, ForeignKey("briefings.id"))
    item = Column(Text)
    your_response = Column(Text)
    action_taken = Column(Text)
    decided_at = Column(DateTime, default=datetime.utcnow)


class Approval(Base):
    __tablename__ = "approvals"
    id = Column(Integer, primary_key=True)
    agent = Column(String(64))
    content_type = Column(String(64))
    content_text = Column(Text)
    platform = Column(String(64))
    status = Column(String(16), default="pending")
    requested_at = Column(DateTime, default=datetime.utcnow)
    decided_at = Column(DateTime)


class SmsLog(Base):
    __tablename__ = "sms_log"
    id = Column(Integer, primary_key=True)
    direction = Column(String(8))  # "in" or "out"
    body = Column(Text)
    from_number = Column(String(32))
    to_number = Column(String(32))
    created_at = Column(DateTime, default=datetime.utcnow)


class MarketSignal(Base):
    __tablename__ = "market_signals"
    id = Column(Integer, primary_key=True)
    source = Column(String(128))
    headline = Column(Text)
    relevance_score = Column(Float, default=0.0)
    flagged_for_briefing = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ContentQueue(Base):
    __tablename__ = "content_queue"
    id = Column(Integer, primary_key=True)
    platform = Column(String(64))
    content_text = Column(Text)
    status = Column(String(16), default="pending")
    scheduled_for = Column(DateTime)
    posted_at = Column(DateTime)
    performance_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialised")


def _session() -> Session:
    return SessionLocal()


def log_agent_run(
    agent_name: str,
    status: str,
    summary: Optional[str],
    raw: Optional[str],
    duration: Optional[float],
) -> AgentRun:
    with _session() as s:
        run = AgentRun(
            agent_name=agent_name,
            run_date=date.today().isoformat(),
            status=status,
            output_summary=summary,
            raw_output=raw,
            duration_seconds=duration,
        )
        s.add(run)
        s.commit()
        s.refresh(run)
        return run


def save_briefing(
    date_str: str,
    business: str,
    marketing: str,
    finance: str,
    guide: str,
    full_text: str,
) -> Briefing:
    with _session() as s:
        briefing = Briefing(
            date=date_str,
            business_section=business,
            marketing_section=marketing,
            finance_section=finance,
            guide_section=guide,
            full_text=full_text,
        )
        s.add(briefing)
        s.commit()
        s.refresh(briefing)
        return briefing


def update_briefing(
    date_str: str,
    audio_url: Optional[str] = None,
    call_sid: Optional[str] = None,
) -> None:
    with _session() as s:
        briefing = s.query(Briefing).filter(Briefing.date == date_str).first()
        if briefing:
            if audio_url is not None:
                briefing.audio_url = audio_url
            if call_sid is not None:
                briefing.call_sid = call_sid
            s.commit()


def log_decision(
    briefing_id: int,
    item: str,
    response: str,
    action: str,
) -> Decision:
    with _session() as s:
        decision = Decision(
            briefing_id=briefing_id,
            item=item,
            your_response=response,
            action_taken=action,
        )
        s.add(decision)
        s.commit()
        s.refresh(decision)
        return decision


def log_approval(
    agent: str,
    content_type: str,
    content_text: str,
    platform: str,
) -> Approval:
    with _session() as s:
        approval = Approval(
            agent=agent,
            content_type=content_type,
            content_text=content_text,
            platform=platform,
        )
        s.add(approval)
        s.commit()
        s.refresh(approval)
        return approval


def update_approval_status(approval_id: int, status: str) -> None:
    with _session() as s:
        approval = s.query(Approval).filter(Approval.id == approval_id).first()
        if approval:
            approval.status = status
            approval.decided_at = datetime.utcnow()
            s.commit()


def log_sms(
    direction: str,
    body: str,
    from_num: str,
    to_num: str,
) -> SmsLog:
    with _session() as s:
        entry = SmsLog(direction=direction, body=body, from_number=from_num, to_number=to_num)
        s.add(entry)
        s.commit()
        s.refresh(entry)
        return entry


def save_signal(
    source: str,
    headline: str,
    score: float,
    flagged: bool,
) -> MarketSignal:
    with _session() as s:
        signal = MarketSignal(
            source=source,
            headline=headline,
            relevance_score=score,
            flagged_for_briefing=flagged,
        )
        s.add(signal)
        s.commit()
        s.refresh(signal)
        return signal


def get_pending_approvals() -> list[Approval]:
    with _session() as s:
        return s.query(Approval).filter(Approval.status == "pending").all()


def get_todays_briefing() -> Optional[Briefing]:
    with _session() as s:
        return s.query(Briefing).filter(Briefing.date == date.today().isoformat()).first()


def get_recent_signals(n: int = 10) -> list[MarketSignal]:
    with _session() as s:
        return (
            s.query(MarketSignal)
            .order_by(MarketSignal.created_at.desc())
            .limit(n)
            .all()
        )
