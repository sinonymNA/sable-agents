import os
import re
import time

from anthropic import Anthropic
from loguru import logger

_MODEL = "claude-haiku-4-5-20251001"
_CLAUDE_TIMEOUT = 6.0

_sessions: dict[str, dict] = {}

VOICES = {
    "marcus":  "Polly.Matthew",
    "jt":      "Polly.Joey",
    "trade":   "Polly.Brian",
    "content": "Polly.Joanna",
    "finance": "Polly.Emma",
}

AGENT_LABELS = {
    "jt":      "JT, Sales Scout",
    "trade":   "Trade Monitor",
    "content": "Content Scout",
    "finance": "Finance Agent",
}

_COS_SYSTEM = """You are Marcus, Chief of Staff for Sable Agents — an autonomous income system run by Ethan.

Your role: answer calls from Ethan, brief him on what's happening, take direction, and pull in specialist agents when relevant.

Specialist agents you can summon:
- jt (Sales Scout): FreshUp AI dealership sales, JT's pipeline and daily actions
- trade (Trade Monitor): Sable Stocks paper trading, gate status, daily P&L
- content (Content Scout): Substack ideas for Micah Eres — AI, finance, education, autonomous income
- finance (Finance Agent): Weekly P&L, income vs expenses, financial position

To bring in an agent, finish your sentence and include exactly this tag: [AGENT:jt] or [AGENT:trade] or [AGENT:content] or [AGENT:finance]

Example: "That touches on the trade gate — let me pull in the Trade Monitor. [AGENT:trade]"

Rules:
- Keep your own responses under 3 sentences before any handoff
- Sound calm, sharp, and direct — not robotic or over-formal
- Current system state: paper trading active, gate day 1 of 20, zero income, $167 in expenses (Apex evaluation fee)
- After an agent speaks, briefly frame what they said or ask if Ethan wants to go deeper
- Always end with a question or "anything else?" to keep the conversation going
- If Ethan says goodbye, thanks, or done — respond warmly and end your reply with exactly: [END]
"""

_AGENT_SYSTEMS = {
    "jt": """You are JT, Chief Sales Officer at Sable Agents, on a live call with Ethan. Marcus just pulled you in.
You sell FreshUp AI: an AI phone sales training simulator for automotive dealerships at $399/month per location.
Be direct, confident, and specific. Under 3 sentences. End with a concrete action or number.""",

    "trade": """You are the Trade Monitor at Sable Agents, on a live call with Ethan. Marcus just pulled you in.
You track the Sable Stocks paper trading account. Current state: gate day 1 of 20, daily P&L $0, status active, no trades yet.
Be precise and analytical. Under 3 sentences. Give a clear status and one thing to watch.""",

    "content": """You are the Content Scout at Sable Agents, on a live call with Ethan. Marcus just pulled you in.
You generate Substack ideas for Micah Eres. Themes: AI, personal finance, education, autonomous income. Voice: direct, serious, no hype.
Under 3 sentences. Give one sharp idea or observation.""",

    "finance": """You are the Finance Agent at Sable Agents, on a live call with Ethan. Marcus just pulled you in.
Current position: Income $0, Expenses $167 (Apex evaluation fee), paper trading active, week 1 of operations.
Speak like a sharp CFO. Under 3 sentences. Be direct about the position and what needs to happen.""",
}


def get_session(call_sid: str) -> dict:
    if call_sid not in _sessions:
        _sessions[call_sid] = {"history": []}
    return _sessions[call_sid]


def clear_session(call_sid: str) -> None:
    _sessions.pop(call_sid, None)


def _call_claude(system: str, messages: list, max_tokens: int, label: str) -> str:
    """Call Claude with a tight timeout and one retry. Raises on final failure."""
    client = Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        timeout=_CLAUDE_TIMEOUT,
    )
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            response = client.messages.create(
                model=_MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            return response.content[0].text.strip()
        except Exception as exc:
            last_exc = exc
            logger.warning(
                f"{label} Claude attempt {attempt + 1} failed: {type(exc).__name__}: {exc}"
            )
            if attempt == 0:
                time.sleep(0.3)
    assert last_exc is not None
    raise last_exc


def marcus_respond(call_sid: str, user_input: str) -> tuple[list[dict], bool]:
    """
    Process user speech and return (segments, should_end).
    Each segment is {voice, text}.
    """
    session = get_session(call_sid)
    session["history"].append({"role": "user", "content": user_input})

    try:
        marcus_text = _call_claude(
            system=_COS_SYSTEM,
            messages=session["history"],
            max_tokens=300,
            label="Marcus",
        )
    except Exception as exc:
        logger.error(f"Marcus Claude call failed after retry: {type(exc).__name__}: {exc}")
        marcus_text = "I'm getting a connection hiccup. Can you say that one more time?"

    session["history"].append({"role": "assistant", "content": marcus_text})

    should_end = "[END]" in marcus_text
    marcus_text = marcus_text.replace("[END]", "").strip()

    # Split on [AGENT:name] tags
    parts = re.split(r'\[AGENT:(\w+)\]', marcus_text)
    segments: list[dict] = []

    i = 0
    while i < len(parts):
        text = parts[i].strip()
        if text:
            segments.append({"voice": VOICES["marcus"], "text": text})
        i += 1
        if i < len(parts):
            agent_name = parts[i].strip()
            agent_text = _get_agent_response(agent_name, session["history"])
            if agent_text:
                label = AGENT_LABELS.get(agent_name, agent_name.title())
                segments.append({
                    "voice": VOICES.get(agent_name, VOICES["marcus"]),
                    "text": f"{label} here. {agent_text}",
                })
            i += 1

    if not segments:
        segments.append({"voice": VOICES["marcus"], "text": "Sorry, could you repeat that?"})

    return segments, should_end


def _get_agent_response(agent_name: str, history: list) -> str:
    system = _AGENT_SYSTEMS.get(agent_name)
    if not system:
        logger.warning(f"Unknown agent requested: {agent_name}")
        return ""
    try:
        return _call_claude(
            system=system,
            messages=history[-6:],
            max_tokens=128,
            label=f"Agent[{agent_name}]",
        )
    except Exception as exc:
        logger.error(f"Agent {agent_name} response failed after retry: {type(exc).__name__}: {exc}")
        fallbacks = {
            "jt": "Focus today on dealerships with under fifty reps — they decide faster. Call three by noon.",
            "trade": "Still on day one of the twenty-day gate. No trades yet. Paper account is clean.",
            "content": "Write about the gap between people who talk about building systems and people who ship them. That's the lane.",
            "finance": "Week one position: zero revenue, a hundred and sixty-seven in expenses. Runway is fine. Ship product.",
        }
        return fallbacks.get(agent_name, "I'm offline at the moment. Try again shortly.")
