import os
import re

from anthropic import Anthropic
from loguru import logger

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


def marcus_respond(call_sid: str, user_input: str) -> tuple[list[dict], bool]:
    """
    Process user speech and return (segments, should_end).
    Each segment is {voice, text}.
    """
    session = get_session(call_sid)
    session["history"].append({"role": "user", "content": user_input})

    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    try:
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=300,
            system=_COS_SYSTEM,
            messages=session["history"],
        )
        marcus_text = response.content[0].text.strip()
    except Exception as exc:
        logger.error(f"Marcus Claude call failed: {exc}")
        marcus_text = "I'm having trouble right now. Try again in a moment."

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
    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    try:
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=128,
            system=system,
            messages=history[-6:],
        )
        return response.content[0].text.strip()
    except Exception as exc:
        logger.error(f"Agent {agent_name} response failed: {exc}")
        return "I'm having trouble connecting right now."
