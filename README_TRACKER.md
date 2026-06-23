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

## Optional: auto-post to social (Facebook Page)

When a **strong** signal fires, the agent can generate a post and publish it to
your Facebook Page automatically. Copy comes from the LLM when budget is
available, otherwise a free template; an optional branded image card is attached.

```env
PUBLISH_ENABLED=true
PUBLISH_DRY_RUN=true            # leave true to preview; set false to actually post
PUBLISH_MIN_CONFIDENCE=0.7      # only post strong signals
POST_IMAGE=true                 # branded card (needs Pillow); text-only otherwise
FB_PAGE_ID=...
FB_PAGE_ACCESS_TOKEN=...        # long-lived Page token with pages_manage_posts
```

- **Dry-run by default.** With `PUBLISH_DRY_RUN=true` (or no FB token) it prints
  exactly what it *would* post — flip to `false` only when you're ready to go live.
- **Gated** by `PUBLISH_MIN_CONFIDENCE` so only high-confidence events post, and
  by the same dedup/leader logic as alerts (no double-posting across instances).
- **Pluggable:** add platforms by subclassing
  [`publish.base.Publisher`](stock_tracker/publish/base.py) — X, LinkedIn, etc.
  follow the same shape. (TikTok/Reels need video, a separate build.)

### Instagram

Instagram uses the same Graph API (Business/Creator account linked to your Page,
app scope `instagram_content_publish`). One key difference: **IG fetches the
image by URL** rather than accepting an upload, so the card must be publicly
hosted. Write cards to a served directory and tell the agent its public URL:

```env
IG_USER_ID=...                         # IG business account id
IG_ACCESS_TOKEN=...                    # or leave blank to reuse FB_PAGE_ACCESS_TOKEN
IMAGE_OUTPUT_DIR=/var/www/cards        # where cards are written
IMAGE_PUBLIC_BASE_URL=https://you.com/cards   # how that dir is reachable
```

Publishing is the standard two-step flow (create media container → publish).
FB and IG can run live at the same time; both are gated by the same confidence
threshold and dedup. Without a public image URL, IG posts are skipped (it can't
do text-only) — Facebook still posts.

> ⚠️ Auto-posting financial content carries platform-ToS and "is this advice?"
> exposure. A disclaimer is appended to every post; consider `PUBLISH_DRY_RUN`
> or a review step for anything sensitive.

Full step-by-step (Meta app, Page token, Instagram linking, serving the card
image on your VM): [`deploy/meta-setup.md`](deploy/meta-setup.md).

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
