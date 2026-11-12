#!/usr/bin/env python3
"""
pricing_harness.py — Minimal regression harness for the ShipFast AI Pricing Agent.

Evaluates agent output against agreed price ranges per input segment.
The agent is mocked — we are testing the harness design, not a real LLM.

Run: python pricing_harness.py
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class PricingInput:
    weight_kg: float
    distance_km: float
    service: str
    customer_tier: str = "standard"


@dataclass
class PriceRange:
    min_usd: float
    max_usd: float

    def contains(self, price: float) -> bool:
        return self.min_usd <= price <= self.max_usd


@dataclass
class HarnessResult:
    input: PricingInput
    expected_range: PriceRange
    actual_price: float
    passed: bool
    model_version: str
    latency_ms: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_log_dict(self) -> dict:
        return {
            "input": self.input.__dict__,
            "expected_range": {"min": self.expected_range.min_usd, "max": self.expected_range.max_usd},
            "actual_price": self.actual_price,
            "passed": self.passed,
            "model_version": self.model_version,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Agreed price ranges — defined by product/pricing team, not by the model
# Format: (weight_band, distance_band, service, customer_tier) → PriceRange
# ---------------------------------------------------------------------------

PRICE_RANGES: dict[tuple, PriceRange] = {
    ("medium", "medium",  "STANDARD",  "standard"):   PriceRange(35.0,  55.0),
    ("medium", "medium",  "STANDARD",  "enterprise"): PriceRange(30.0,  48.0),
    ("light",  "short",   "EXPRESS",   "standard"):   PriceRange(12.0,  20.0),
    ("heavy",  "long",    "OVERNIGHT", "standard"):   PriceRange(120.0, 180.0),
    ("light",  "medium",  "STANDARD",  "standard"):   PriceRange(20.0,  35.0),
}


def classify_weight(kg: float) -> str:
    if kg < 2:       return "light"
    elif kg <= 20:   return "medium"
    else:            return "heavy"


def classify_distance(km: float) -> str:
    if km < 20:      return "short"
    elif km <= 100:  return "medium"
    else:            return "long"


def get_expected_range(inp: PricingInput) -> Optional[PriceRange]:
    key = (
        classify_weight(inp.weight_kg),
        classify_distance(inp.distance_km),
        inp.service,
        inp.customer_tier,
    )
    return PRICE_RANGES.get(key)


# ---------------------------------------------------------------------------
# Mocked pricing agent — replace call_pricing_agent() with the real client
# ---------------------------------------------------------------------------

def build_mock_agent():
    """Returns a mock agent that simulates normal and outlier behaviour."""
    agent = MagicMock()
    agent.model_version = "pricing-agent-v2.1.0"

    def mock_predict(payload: dict) -> dict:
        import time
        time.sleep(0.001)  # simulate latency
        # Simulate known outlier: enterprise tier + medium weight triggers bad output
        if payload.get("customer_tier") == "enterprise" and 10 <= payload.get("weight_kg", 0) <= 15:
            return {"price_usd": 4210.00}  # known outlier from assignment
        # Normal outputs within expected range
        base = 10.0 + payload.get("weight_kg", 1) * 1.5 + payload.get("distance_km", 1) * 0.1
        return {"price_usd": round(base, 2)}

    agent.predict = mock_predict
    return agent


def call_pricing_agent(agent, inp: PricingInput) -> tuple[float, float]:
    """Call the agent and return (price_usd, latency_ms)."""
    import time
    start = time.monotonic()
    result = agent.predict(inp.__dict__)
    latency_ms = (time.monotonic() - start) * 1000
    return result["price_usd"], latency_ms


# ---------------------------------------------------------------------------
# Golden dataset — 200+ inputs in production; this is a representative sample
# ---------------------------------------------------------------------------

GOLDEN_DATASET = [
    PricingInput(weight_kg=12,  distance_km=80,  service="STANDARD",  customer_tier="standard"),
    PricingInput(weight_kg=12,  distance_km=80,  service="STANDARD",  customer_tier="enterprise"),  # known outlier
    PricingInput(weight_kg=0.5, distance_km=5,   service="EXPRESS",   customer_tier="standard"),
    PricingInput(weight_kg=25,  distance_km=200, service="OVERNIGHT", customer_tier="standard"),
    PricingInput(weight_kg=1.0, distance_km=60,  service="STANDARD",  customer_tier="standard"),
]


# ---------------------------------------------------------------------------
# Harness runner
# ---------------------------------------------------------------------------

def run_harness(dataset: list[PricingInput], agent) -> list[HarnessResult]:
    results = []
    for inp in dataset:
        expected_range = get_expected_range(inp)
        if expected_range is None:
            logger.warning(f"No agreed range for input: {inp} — skipping")
            continue
        actual_price, latency_ms = call_pricing_agent(agent, inp)
        passed = expected_range.contains(actual_price)
        result = HarnessResult(
            input=inp,
            expected_range=expected_range,
            actual_price=actual_price,
            passed=passed,
            model_version=agent.model_version,
            latency_ms=round(latency_ms, 2),
        )
        # Structured log for every invocation — forensics trail
        logger.info(json.dumps(result.to_log_dict()))
        results.append(result)
    return results


def report(results: list[HarnessResult]) -> int:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    outlier_rate = (failed / total * 100) if total > 0 else 0

    print(f"\n{'='*55}")
    print(f"  Pricing Regression Harness — {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'='*55}")
    print(f"  Total cases : {total}")
    print(f"  Passed      : {passed}")
    print(f"  Failed      : {failed}")
    print(f"  Outlier rate: {outlier_rate:.1f}%")
    print(f"{'='*55}")

    if failed > 0:
        print("\n  FAILURES:")
        for r in results:
            if not r.passed:
                print(f"  - {r.input} → ${r.actual_price:.2f} "
                      f"(expected ${r.expected_range.min_usd}–${r.expected_range.max_usd})")

    # Drift alert threshold: >2% outlier rate is a release blocker
    if outlier_rate > 2.0:
        print(f"\n  [ALERT] Outlier rate {outlier_rate:.1f}% exceeds 2% threshold — RELEASE BLOCKED")
        return 1
    return 0


if __name__ == "__main__":
    import sys
    agent = build_mock_agent()
    results = run_harness(GOLDEN_DATASET, agent)
    exit_code = report(results)
    sys.exit(exit_code)
