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
