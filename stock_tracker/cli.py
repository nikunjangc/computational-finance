"""Command-line entry point.

Examples
--------
    # Offline end-to-end demo (no keys, no network):
    python -m stock_tracker.cli --demo

    # Classify a single line of text:
    python -m stock_tracker.cli --text "Trump said we will lead in quantum computing"

    # Live agentic mode (uses env config for sources + notifiers):
    python -m stock_tracker.cli --live
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from .agent import Agent, build_default_sources
from .config import Config
from .coordination import build_coordinator
from .knowledge_base import KnowledgeBase
from .notify.base import format_alert
from .notify.dispatcher import Dispatcher, build_notifiers
from .signals.engine import SignalEngine
from .sources.mock_feed import MockFeedSource


def _setup_logging(verbose: bool):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def cmd_text(text: str) -> None:
    engine = SignalEngine()
    signals = engine.process_text(text)
    if not signals:
        print("No sector signals detected.")
        return
    for s in signals:
        print(format_alert(s, markdown=False))
        print("-" * 60)


async def cmd_demo(verbose: bool) -> None:
    cfg = Config.from_env()
    engine = SignalEngine(min_confidence=cfg.min_confidence)
    dispatcher = Dispatcher(build_notifiers(cfg, include_console=True))
    agent = Agent(sources=[MockFeedSource(delay=0.5)], engine=engine, dispatcher=dispatcher)
    await agent.run()
    print(f"\nDemo complete. processed={agent.processed} alerts={agent.alerts}")


async def cmd_live() -> None:
    cfg = Config.from_env()
    engine = SignalEngine(min_confidence=cfg.min_confidence)
    dispatcher = Dispatcher(build_notifiers(cfg, include_console=True))
    sources = build_default_sources(cfg)
    coordinator = build_coordinator(cfg)
    logging.getLogger("stock_tracker").info(
        "instance=%s role=%s (redis=%s)", coordinator.instance_id, coordinator.role(), bool(cfg.redis_url)
    )
    agent = Agent(sources=sources, engine=engine, dispatcher=dispatcher, coordinator=coordinator)

    # Graceful shutdown on SIGTERM/SIGINT (e.g. `docker stop`).
    loop = asyncio.get_running_loop()
    runner = asyncio.ensure_future(agent.run(heartbeat_seconds=300))
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, runner.cancel)
        except (NotImplementedError, ValueError):
            pass  # not supported on this platform (e.g. Windows)
    try:
        await runner
    except asyncio.CancelledError:
        pass


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="stock_tracker", description="Live agentic market-event tracker")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--demo", action="store_true", help="run offline end-to-end demo with sample transcripts")
    g.add_argument("--live", action="store_true", help="run live agentic mode using env-configured sources")
    g.add_argument("--text", type=str, help="classify a single piece of text and exit")
    g.add_argument("--list-sectors", action="store_true", help="print the loaded sectors and tickers")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    _setup_logging(args.verbose)

    if args.text:
        cmd_text(args.text)
    elif args.list_sectors:
        kb = KnowledgeBase.load()
        for key, sector in kb.sectors.items():
            syms = ", ".join(t.symbol for t in sector.tickers)
            print(f"{sector.display}  [{sector.bias.value}]\n  keywords: {', '.join(sector.keywords)}\n  tickers: {syms}\n")
    elif args.demo:
        asyncio.run(cmd_demo(args.verbose))
    elif args.live:
        asyncio.run(cmd_live())


if __name__ == "__main__":
    main()
