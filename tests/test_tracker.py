"""Tests for the stock_tracker pipeline (run: python -m pytest tests/)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_tracker.coordination import RedisCoordinator, RoleCoordinator
from stock_tracker.knowledge_base import KnowledgeBase
from stock_tracker.models import Direction, Signal, TickerHit, Utterance
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


# ----------------------- coordination / dedup -------------------------

def _signal(text="Trump backs quantum computing, it will go up", speaker="Trump"):
    return SignalEngine().process_text(text, speaker=speaker)[0]


def test_fingerprint_stable_across_instances():
    # Same event seen by two separate agents -> identical fingerprint.
    a = _signal()
    b = _signal()
    assert a.fingerprint() == b.fingerprint()
    # A different event differs.
    c = _signal(text="We will hike the interest rate and keep policy tight", speaker="Powell")
    assert a.fingerprint() != c.fingerprint()


def test_role_coordinator_primary_emits_standby_silent():
    primary = RoleCoordinator(role="primary")
    standby = RoleCoordinator(role="standby")
    sig = _signal()
    assert primary.claim(sig) is True
    assert standby.claim(sig) is False


class _FakeRedis:
    """Minimal in-memory Redis supporting the set(nx/xx/px/ex)/get we use."""

    def __init__(self):
        self.store = {}

    def set(self, key, val, nx=False, xx=False, px=None, ex=None):
        exists = key in self.store
        if nx and exists:
            return None
        if xx and not exists:
            return None
        self.store[key] = val
        return True

    def get(self, key):
        return self.store.get(key)


def test_redis_coordinator_single_alert_across_two_instances():
    shared = _FakeRedis()
    c1 = RedisCoordinator("redis://x", instance_id="oracle", client=shared)
    c2 = RedisCoordinator("redis://x", instance_id="gcp", client=shared)
    sig = _signal()
    # Both instances see the same event; exactly one should win the claim.
    r1 = c1.claim(sig)
    r2 = c2.claim(sig)
    assert sum([r1, r2]) == 1, "exactly one instance must send the alert"


def test_redis_coordinator_failover_standby_takes_over():
    shared = _FakeRedis()
    leader = RedisCoordinator("redis://x", instance_id="oracle", client=shared, lease_ttl=30)
    standby = RedisCoordinator("redis://x", instance_id="gcp", client=shared, lease_ttl=30)
    # Leader is active first.
    assert leader.claim(_signal(text="quantum computing rallies", speaker="A")) is True
    assert standby._acquire_or_renew() is False
    # Simulate the leader dying: its lease key expires.
    shared.store.clear()
    # Standby can now acquire leadership and emit.
    assert standby.claim(_signal(text="quantum computing rallies again", speaker="B")) is True


# ----------------------- LLM classifier (budget-capped) ---------------

import tempfile
import types

from stock_tracker.nlp.llm_classifier import CostTracker, LLMClassifier


def _tracker(budget=1.0):
    path = tempfile.mktemp(suffix=".json")
    return CostTracker(path, budget)


def test_cost_tracker_records_and_caps():
    t = _tracker(budget=0.01)
    assert t.can_spend()
    usage = {"input_tokens": 2000, "output_tokens": 100, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    cost = t.record(usage, "claude-haiku-4-5")
    assert cost > 0
    # 2000 in @ $1/M + 100 out @ $5/M = 0.002 + 0.0005 = 0.0025
    assert abs(cost - 0.0025) < 1e-6
    assert t.spent() == cost


def test_cost_tracker_budget_blocks_when_exhausted():
    t = _tracker(budget=0.001)
    t.record({"input_tokens": 5000, "output_tokens": 0}, "claude-haiku-4-5")  # $0.005 > budget
    assert not t.can_spend()


class _FakeUsage:
    input_tokens = 1500
    output_tokens = 50
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 0


class _FakeMessages:
    def __init__(self, text):
        self._text = text

    def create(self, **kwargs):
        block = types.SimpleNamespace(type="text", text=self._text)
        return types.SimpleNamespace(content=[block], usage=_FakeUsage())


class _FakeClient:
    def __init__(self, text):
        self.messages = _FakeMessages(text)


def test_llm_classifier_parses_and_charges():
    kb = KnowledgeBase.load()
    t = _tracker(budget=1.0)
    fake = _FakeClient('{"sectors":[{"key":"quantum_computing","direction":"bullish","confidence":0.9}],"reason":"x"}')
    clf = LLMClassifier("key", "claude-haiku-4-5", kb, t, client=fake)
    matches = clf.classify("Trump talked up quantum computing")
    assert matches and matches[0].sector.key == "quantum_computing"
    assert matches[0].direction == Direction.BULLISH
    assert t.spent() > 0  # the call was charged


def test_llm_classifier_falls_back_when_budget_hit():
    kb = KnowledgeBase.load()
    t = _tracker(budget=0.0)  # no budget
    fake = _FakeClient('{"sectors":[]}')
    clf = LLMClassifier("key", "claude-haiku-4-5", kb, t, client=fake)
    assert clf.classify("anything") is None  # signals fall back to free matcher


def test_engine_uses_llm_when_candidate_present():
    kb = KnowledgeBase.load()
    t = _tracker(budget=1.0)
    # LLM flips the crypto sector bearish even though text reads bullish-ish.
    fake = _FakeClient('{"sectors":[{"key":"crypto_digital_assets","direction":"bearish","confidence":0.8}],"reason":"r"}')
    clf = LLMClassifier("key", "claude-haiku-4-5", kb, t, client=fake)
    engine = SignalEngine(kb=kb, llm=clf)
    signals = engine.process_text("bitcoin and crypto are in the news")
    assert any(s.sector_key == "crypto_digital_assets" and s.direction == Direction.BEARISH for s in signals)


if __name__ == "__main__":
    # Allow running without pytest installed.
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} tests passed")
