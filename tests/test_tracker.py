"""Tests for the stock_tracker pipeline (run: python -m pytest tests/)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_tracker.knowledge_base import KnowledgeBase
from stock_tracker.models import Direction, Utterance
from stock_tracker.nlp.bag_of_words import BagOfWordsMatcher
from stock_tracker.signals.engine import SignalEngine


def test_kb_loads():
    kb = KnowledgeBase.load()
    assert "quantum_computing" in kb.sectors
    assert "IONQ" in [t.symbol for t in kb.sectors["quantum_computing"].tickers]
    assert kb.bullish and kb.bearish


def test_quantum_detection_bullish():
    engine = SignalEngine()
    signals = engine.process_text(
        "We will lead the world in quantum computing, it is going to go up and be a huge winner."
    )
    sectors = {s.sector_key for s in signals}
    assert "quantum_computing" in sectors
    q = next(s for s in signals if s.sector_key == "quantum_computing")
    assert q.direction == Direction.BULLISH
    assert "IONQ" in q.symbols


def test_crypto_and_cryptography_both_match():
    engine = SignalEngine()
    signals = engine.process_text("On cryptography and crypto, Bitcoin and blockchain are the future.")
    keys = {s.sector_key for s in signals}
    assert "crypto_digital_assets" in keys
    assert "cryptography_post_quantum" in keys


def test_negation_flips_direction():
    matcher = BagOfWordsMatcher(KnowledgeBase.load())
    matches = matcher.match("We will not support crypto and want to ban bitcoin trading.")
    crypto = next(m for m in matches if m.sector.key == "crypto_digital_assets")
    assert crypto.direction == Direction.BEARISH


def test_hawkish_fed_is_bearish():
    engine = SignalEngine()
    signals = engine.process_text("We are prepared to hike the interest rate and keep policy tight.")
    fed = next(s for s in signals if s.sector_key == "interest_rates_fed")
    assert fed.direction == Direction.BEARISH


def test_neutral_text_no_signal():
    engine = SignalEngine()
    signals = engine.process_text("Markets were mixed today as investors weighed earnings reports.")
    assert signals == []


def test_confidence_in_range():
    engine = SignalEngine()
    for s in engine.process_text("quantum computing qubit quantum chip will go up"):
        assert 0.0 <= s.confidence <= 1.0


if __name__ == "__main__":
    # Allow running without pytest installed.
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} tests passed")
