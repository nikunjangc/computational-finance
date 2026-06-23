# 📈 Live Agentic Market-Event Tracker (`stock_tracker`)

Listen to live market commentary — CNBC / Yahoo Finance YouTube live streams,
the FOMC / economic calendar, crypto indices, generic websocket feeds — detect
when a market mover (the **Fed Chair**, the **President**, a policy maker)
mentions a theme, map that theme to the **related stocks**, and push an alert
to **Telegram / WhatsApp**.

> Example: *"Today Trump said we will lead in **quantum computing** and
> **cryptography**…"* →
> 🟢 **BULLISH · Quantum Computing** → `IONQ, RGTI, QBTS, QUBT, IBM, GOOGL`
> → alert sent to Telegram.

This is the idea from the reel you shared, turned into an automated agent: a
transparent **bag-of-words** knowledge base routes spoken themes to the tickers
that historically react, and an async agent fires the alert the moment the
event happens.

---

## Quick start

```bash
pip install -r requirements-tracker.txt        # PyYAML + requests (core)

# 1) Offline end-to-end demo — no keys, no network:
python run_tracker.py --demo

# 2) Classify a single headline / quote:
python run_tracker.py --text "Trump: we will dominate quantum computing, stocks will go up"

# 3) See the sector → ticker knowledge base:
python run_tracker.py --list-sectors

# 4) Live agentic mode (uses your .env config):
cp .env.example .env    # fill in tokens for the sources/notifiers you have
python run_tracker.py --live
```

Run the tests with `python tests/test_tracker.py` (or `pytest tests/`).

---

## Run it continuously (Docker)

The agent is long-running — the FOMC calendar and crypto-index pollers stay
scheduled inside it, and the YouTube/websocket sources stream live — so the
intended deployment is a single always-on container.

```bash
cp .env.example .env            # fill in your tokens / channels
docker compose up -d --build    # start in the background
docker compose logs -f tracker  # watch alerts stream in real time
```

- `restart: unless-stopped` keeps it alive across crashes and reboots.
- It handles `SIGTERM`/`SIGINT`, so `docker compose stop` shuts down cleanly.
- A heartbeat line is logged every 5 min so you can confirm it's alive.
- One-off smoke test in the image: `docker compose run --rm tracker --demo`.

No Docker? Run it under any process supervisor instead:

```bash
# systemd / supervisord / pm2 / nohup — all work; it just needs to stay up:
python run_tracker.py --live
```

The image installs the optional live connectors (`youtube-transcript-api`,
`websockets`) so live mode is fully functional in the container.

**Hosting it 24/7:** a long-running worker needs a real host — *not* GitHub
Actions (job-only, ~6 h cap) or Vercel (serverless, short-lived). Use an
always-on VPS or worker platform. A step-by-step guide for the **Oracle Cloud
free ARM tier** is in [`deploy/oracle-cloud.md`](deploy/oracle-cloud.md), with a
ready-to-use systemd unit in [`deploy/stock-tracker.service`](deploy/stock-tracker.service).

### High availability (primary + failover, no double alerts)

Run a second instance (e.g. a free GCP `e2-micro`) as a hot standby. The
[`coordination`](stock_tracker/coordination.py) layer makes sure exactly one
host ever sends an alert:

- **Role-based (default, no deps):** `TRACKER_ROLE=primary` on the main host,
  `TRACKER_ROLE=standby` on the backup. The standby runs the full pipeline but
  stays silent; promote it if the primary dies.
- **Redis (automatic):** set the same `REDIS_URL` on both hosts → a leader lease
  auto-fails-over within `LEASE_TTL`s and a per-event dedup key (content
  `fingerprint`) guarantees one alert per event, even active/active.

Full walkthrough: [`deploy/gcp-failover.md`](deploy/gcp-failover.md).

---

## How it works

```
            ┌──────────────── SOURCES (async, concurrent) ────────────────┐
            │                                                             │
  scheduled │  EconomicCalendar (FOMC / Fed meetings)                     │
   "meeting"│  CryptoIndex      (CoinGecko "coin index" moves)            │
            │                                                             │
   push /   │  YouTubeLive      (CNBC / Yahoo Finance live captions)      │
  "socket"  │  WebSocketFeed    (your transcription / news relay)         │
            └───────────────────────────┬─────────────────────────────────┘
                                         │  Utterance(text, speaker, source)
                                         ▼
                          ┌──────────── SignalEngine ────────────┐
                          │  BagOfWordsMatcher  (sectors.yaml)    │
                          │   • keyword/phrase match → sector     │
                          │   • bullish/bearish + negation → dir  │
                          │   • sector → related tickers          │
                          └───────────────────┬───────────────────┘
                                              │  Signal(sector, dir, tickers, conf)
                                              ▼
                          ┌──────────── Dispatcher (dedup) ───────┐
                          │  Telegram · WhatsApp · Console        │
                          └───────────────────────────────────────┘
```

The two trigger paths you asked for:

1. **Scheduled** — `EconomicCalendarSource` fires a heads-up before each known
   FOMC date; `CryptoIndexSource` polls a coin index and fires on big moves.
2. **Live / "open socket"** — `YouTubeLiveSource` polls live caption tracks and
   `WebSocketFeedSource` consumes a push feed (e.g. an audio→text relay of the
   CNBC / Yahoo Finance stream), all funnelled through the same engine.

---

## The "bag of words" (knowledge base)

Everything that maps a spoken theme to stocks lives in
[`stock_tracker/knowledge/sectors.yaml`](stock_tracker/knowledge/sectors.yaml)
— edit it freely. Each sector has trigger `keywords`, the `tickers` that move
with it, and an optional default `bias`:

```yaml
sectors:
  quantum_computing:
    display: "Quantum Computing"
    bias: bullish
    keywords: [quantum, qubit, quantum computing, quantum chip]
    tickers:
      - {symbol: IONQ, name: "IonQ"}
      - {symbol: RGTI, name: "Rigetti Computing"}
      - {symbol: QBTS, name: "D-Wave Quantum"}
```

Direction (🟢 bullish / 🔴 bearish) is inferred from the bullish/bearish
sentiment lexicons in the same file, with local **negation** handling
("we will **not** support crypto" → bearish).

Ships with sectors for: Quantum Computing, Cryptography/Post-Quantum, Crypto,
AI/Semis, Fed/Rates, Energy, Defense, and Tariffs/Trade.

---

## Configuration

All config is environment-driven (see [`.env.example`](.env.example)). Anything
left blank simply disables that connector — the agent keeps running with
whatever is configured, always printing to the console as a fallback.

| Purpose | Variables |
|---|---|
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| WhatsApp (Twilio) | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`, `WHATSAPP_TO` |
| WhatsApp (Meta) | `WHATSAPP_PROVIDER=meta`, `META_WA_TOKEN`, `META_WA_PHONE_ID`, `WHATSAPP_TO` |
| YouTube | `YOUTUBE_CHANNELS` (comma-sep video/live IDs or URLs) |
| Crypto | `CRYPTO_SYMBOLS`, `CRYPTO_MOVE_PCT` |
| WebSocket | `WEBSOCKET_URLS` |

> **Secrets:** never commit your real `.env` (it is git-ignored). The repo only
> contains `.env.example`.

---

## Optional: LLM classifier (≈ $1/month, budget-capped)

The free bag-of-words engine always runs and acts as the **pre-filter**. Turn on
the LLM classifier to have **Claude Haiku** refine the snippets it flags —
catching paraphrases and sarcasm the keyword matcher misses (e.g. *"the Fed will
ease"* with no literal "rate cut").

```env
LLM_ENABLED=true
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=claude-haiku-4-5
LLM_MONTHLY_BUDGET_USD=1.0     # hard cap — falls back to free mode when reached
```

How it stays around a dollar a month:
- It **only** calls the API on snippets the free matcher already flagged — most
  text never reaches Claude.
- The fixed sector guide is sent with **prompt caching**, so repeat calls bill
  the prefix at ~0.1×.
- A persistent [`CostTracker`](stock_tracker/nlp/llm_classifier.py) enforces the
  monthly budget; once spent, `classify()` returns `None` and the engine
  **transparently falls back** to the free matcher until the month rolls over.
- One classification on Haiku ≈ **$0.001–0.0025**, so $1 buys hundreds of LLM
  refinements per month.

If `anthropic` isn't installed, no key is set, or `LLM_ENABLED=false`, the
classifier disables itself and everything runs free.

## Extending it

- **Add a sector / stock** → edit `sectors.yaml`. No code changes.
- **Add a source** → subclass `stock_tracker.sources.base.Source` and implement
  `async def stream(self)` yielding `Utterance`s; register it in
  `agent.build_default_sources`.
- **Add a notifier** → subclass `stock_tracker.notify.base.Notifier`.
- **Smarter classification** → the bag-of-words matcher is intentionally a
  transparent baseline; swap in a transformer / LLM classifier behind the same
  `BagOfWordsMatcher.match` interface.

## Disclaimer

This is research/educational tooling, **not investment advice**. Detected
signals are heuristic and can be wrong; always do your own diligence and respect
the terms of service of any data source (YouTube, exchanges, etc.).
