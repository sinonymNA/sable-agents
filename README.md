# Sable Agents

Four autonomous AI agents run every morning at 5 AM ET, synthesize their
outputs into a voice briefing, and deliver it as a phone call at 6 AM ET.

## Architecture

```
5:00 AM ET
  ├── agents/business.py   → market & business intel
  ├── agents/marketing.py  → trends & content opportunities
  ├── agents/finance.py    → macro & cash-flow awareness
  └── agents/guide.py      → mindset & daily operating system
          │
          ▼
  briefing/synthesizer.py  → Claude weaves four reports into a voice script
          │
          ▼
  briefing/voice.py        → ElevenLabs converts script to MP3
          │
6:00 AM ET
  briefing/call.py         → Twilio places the morning call
```

SMS commands (text your Twilio number):
- `STATUS` — today's briefing status
- `APPROVALS` — list pending content approvals
- `APPROVE <id>` / `REJECT <id>` — act on an approval

## Quick Start

```bash
cp .env.example .env
# fill in your keys

pip install -r requirements.txt

# initialise the database
python -c "from db.models import init_db; init_db(); print('DB OK')"

# run the API (includes scheduler)
uvicorn api.main:app --reload
```

## Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key |
| `ELEVENLABS_API_KEY` | ElevenLabs API key |
| `ELEVENLABS_VOICE_*` | Voice IDs per agent |
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_FROM_NUMBER` | Your Twilio phone number |
| `OPERATOR_PHONE_NUMBER` | Your personal phone for calls & SMS |
| `NEWSAPI_KEY` | NewsAPI key for business/finance agents |
| `DATABASE_URL` | PostgreSQL URL (Railway injects this) |
| `AGENT_RUN_TIME` | Cron time for agents (default `05:00` ET) |
| `BRIEFING_CALL_TIME` | Cron time for call (default `06:00` ET) |
| `DASHBOARD_SECRET` | Secret for dashboard auth |

## Deploy to Railway

1. Connect this repo in Railway
2. Add all env vars from `.env.example`
3. Railway auto-detects `railway.toml` and deploys via nixpacks

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/briefing/today` | Today's briefing |
| GET | `/api/approvals/pending` | Pending approvals |
| POST | `/api/approvals/{id}` | Approve / reject |
| POST | `/api/sms/webhook` | Twilio SMS webhook |
