import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from engine.gen3.events import CausalEvent, FrozenSemanticError, Quote, artifacts, materialize_h01, materialize_h02


ROOT = Path(__file__).parents[1]
REGISTRY = str(ROOT / "config/gen3/tier_a_v3.json")
LINEAGE = {"dataset_fingerprint": "a" * 64, "source": "test"}
T0 = datetime(2025, 1, 2, 1, 0, tzinfo=UTC)


def q(t, mid, spread=0.00002): return Quote(t, mid-spread/2, mid+spread/2)


class EventTests(TestCase):
    def test_h01_boundaries_refractory_and_determinism(self):
        # Baseline is [t0-30m,t0); the observation is (t0-30s,t0].
        rows = [q(T0-timedelta(minutes=30)+timedelta(seconds=3*i), 1.1) for i in range(601)]
        rows.extend(q(T0+timedelta(seconds=3*i), 1.10001*i) for i in range(1, 11))
        one = materialize_h01(rows, registry_path=REGISTRY, dataset_role="DISCOVERY", lineage=LINEAGE)
        two = materialize_h01(list(reversed(rows)), registry_path=REGISTRY, dataset_role="DISCOVERY", lineage=LINEAGE)
        self.assertEqual([x.artifact() for x in one], [x.artifact() for x in two])
        self.assertEqual(1, len(one)); self.assertEqual("LONG", one[0].direction)
        # Zero midpoint changes and insufficient history both fail closed.
        self.assertEqual([], materialize_h01(rows[:10], registry_path=REGISTRY, dataset_role="DISCOVERY", lineage=LINEAGE))
        flat = [q(T0-timedelta(minutes=30)+timedelta(seconds=3*i), 1.1) for i in range(611)]
        self.assertEqual([], materialize_h01(flat, registry_path=REGISTRY, dataset_role="DISCOVERY", lineage=LINEAGE))
        with self.assertRaises(FrozenSemanticError): materialize_h01(rows, registry_path=REGISTRY, dataset_role="FORWARD_LOCKED_HOLDOUT", lineage=LINEAGE)

    def test_h01_gap_and_invalid_quote_fail_closed(self):
        rows = [q(T0-timedelta(minutes=30)+timedelta(seconds=3*i), 1.1) for i in range(601)]
        rows.extend(q(T0+timedelta(seconds=3*i), 1.10001*i) for i in range(1, 11))
        rows[-9] = Quote(rows[-9].timestamp, 0, 1.1)
        self.assertEqual([], materialize_h01(rows, registry_path=REGISTRY, dataset_role="DISCOVERY", lineage=LINEAGE))

    def test_h02_acceptance_completed_minutes_and_hierarchy(self):
        # 61 completed, consecutive midpoint closes before the break; zero returns are retained.
        rows = [q(T0-timedelta(minutes=61-i), 1.0999 if i % 2 == 0 else 1.1001) for i in range(61)]
        rows.extend([q(T0+timedelta(seconds=10), 1.1003)] + [q(T0+timedelta(minutes=i, seconds=10), 1.1005) for i in range(1, 16)])
        events = materialize_h02(rows, registry_path=REGISTRY, dataset_role="DISCOVERY", lineage=LINEAGE)
        self.assertEqual(1, len(events)); self.assertEqual("FIGURE:1.1000", events[0].level_id)
        self.assertEqual(T0+timedelta(minutes=16), events[0].available_at_utc)
        self.assertEqual("ACCEPTANCE", events[0].feature_values["state"])
        self.assertEqual([], materialize_h02(rows[:-1], registry_path=REGISTRY, dataset_role="DISCOVERY", lineage=LINEAGE))

    def test_h02_conflict_and_duplicate_fail_closed(self):
        rows = [q(T0-timedelta(minutes=61-i), 1.0999 if i % 2 == 0 else 1.1001) for i in range(61)] + [q(T0+timedelta(seconds=10), 1.1003)]
        # A hostile classifier reporting both states must never generate an event.
        with patch("engine.gen3.events._post_closes", side_effect=lambda _c, start, count: [(start+timedelta(minutes=i), 1.1005 if count == 15 and start.minute == 1 else 1.0995) for i in range(count)]):
            self.assertEqual([], materialize_h02(rows, registry_path=REGISTRY, dataset_role="DISCOVERY", lineage=LINEAGE))
        e = CausalEvent("H", "x", T0, T0, "LONG", "DISCOVERY", LINEAGE, {}, {}, ())
        self.assertEqual(1, len(artifacts([e])))
        with self.assertRaises(FrozenSemanticError): artifacts([e, e])
        self.assertFalse(any(word in json.dumps(artifacts([e])).lower() for word in ("outcome", "return", "expectancy", "win_rate")))
