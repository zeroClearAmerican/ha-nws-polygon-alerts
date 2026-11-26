"""Standalone tests for alerts.py (no Home Assistant needed).

Run:  python3 -m unittest discover tests
"""

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
import unittest

_PATH = Path(__file__).parents[1] / "custom_components/nws_polygon_alerts/alerts.py"
_spec = importlib.util.spec_from_file_location("alerts", _PATH)
alerts = importlib.util.module_from_spec(_spec)
sys.modules["alerts"] = alerts
_spec.loader.exec_module(alerts)

NOW = datetime(2026, 5, 1, 18, 0, tzinfo=timezone.utc)
LATER = (NOW + timedelta(minutes=30)).isoformat()

# Square around Broken Arrow, OK with a hole in the NE corner. [lon, lat].
SQUARE = [[-96.0, 35.8], [-95.5, 35.8], [-95.5, 36.2], [-96.0, 36.2], [-96.0, 35.8]]
HOLE = [[-95.7, 36.1], [-95.6, 36.1], [-95.6, 36.15], [-95.7, 36.15], [-95.7, 36.1]]
HOME = (36.033152, -95.765713)


def feature(id_, event="Tornado Warning", geometry=None, refs=(), ends=LATER, **props):
    return {
        "id": f"https://api.weather.gov/alerts/{id_}",
        "geometry": geometry,
        "properties": {
            "id": id_,
            "event": event,
            "status": "Actual",
            "messageType": props.pop("messageType", "Alert"),
            "headline": f"{event} {id_}",
            "ends": ends,
            "expires": ends,
            "sent": NOW.isoformat(),
            "references": [{"identifier": r} for r in refs],
            **props,
        },
    }


POLY = {"type": "Polygon", "coordinates": [SQUARE]}


class GeometryTests(unittest.TestCase):
    def test_inside_outside(self):
        self.assertTrue(alerts.point_in_geometry(*HOME, POLY))
        self.assertFalse(alerts.point_in_geometry(36.5, -95.7, POLY))
        self.assertFalse(alerts.point_in_geometry(36.0, -94.0, POLY))

    def test_hole(self):
        g = {"type": "Polygon", "coordinates": [SQUARE, HOLE]}
        self.assertFalse(alerts.point_in_geometry(36.12, -95.65, g))
        self.assertTrue(alerts.point_in_geometry(*HOME, g))

    def test_multipolygon_and_none(self):
        far = [[[-80, 30], [-79, 30], [-79, 31], [-80, 30]]]
        g = {"type": "MultiPolygon", "coordinates": [far, [SQUARE]]}
        self.assertTrue(alerts.point_in_geometry(*HOME, g))
        self.assertFalse(alerts.point_in_geometry(*HOME, None))

    def test_concave(self):
        # "C" shape opening east; point in the notch is outside.
        c = [[-96, 35], [-95, 35], [-95, 35.3], [-95.7, 35.3], [-95.7, 35.7],
             [-95, 35.7], [-95, 36], [-96, 36], [-96, 35]]
        g = {"type": "Polygon", "coordinates": [c]}
        self.assertFalse(alerts.point_in_geometry(35.5, -95.3, g))
        self.assertTrue(alerts.point_in_geometry(35.5, -95.9, g))


class MatchTests(unittest.TestCase):
    def match(self, feats, events=("Tornado Warning",), zone=False):
        return alerts.match_alerts(feats, *HOME, set(events), zone, NOW)

    def test_polygon_filtering(self):
        far = {"type": "Polygon", "coordinates": [[[-80, 30], [-79, 30], [-79, 31], [-80, 30]]]}
        m = self.match([feature("a", geometry=POLY), feature("b", geometry=far)])
        self.assertEqual(list(m), ["a"])

    def test_event_toggle(self):
        f = [feature("a", geometry=POLY), feature("b", "Severe Thunderstorm Warning", POLY)]
        self.assertEqual(set(self.match(f)), {"a"})
        self.assertEqual(
            set(self.match(f, ("Tornado Warning", "Severe Thunderstorm Warning"))), {"a", "b"}
        )

    def test_zone_alerts(self):
        f = [feature("w", "Tornado Watch")]
        self.assertEqual(self.match(f, ("Tornado Watch",)), {})
        self.assertEqual(list(self.match(f, ("Tornado Watch",), zone=True)), ["w"])

    def test_skips_cancel_expired_and_tests(self):
        f = [
            feature("c", geometry=POLY, messageType="Cancel"),
            feature("e", geometry=POLY, ends=(NOW - timedelta(minutes=1)).isoformat()),
            feature("t", geometry=POLY, status="Test"),
        ]
        self.assertEqual(self.match(f), {})

    def test_roundtrip(self):
        a = alerts.Alert.from_feature(feature("a", geometry=POLY, refs=("x",)))
        self.assertEqual(alerts.Alert.from_dict(a.as_dict()), a)


class TrackerTests(unittest.TestCase):
    def alert(self, id_, refs=()):
        return alerts.Alert.from_feature(feature(id_, geometry=POLY, refs=refs))

    def test_lifecycle(self):
        t = alerts.AlertTracker()
        a = self.alert("a")
        c = t.update({"a": a})
        self.assertEqual([x.id for x in c.new], ["a"])

        c = t.update({"a": a})  # unchanged → nothing
        self.assertFalse(c.new or c.updated or c.cleared)

        a2 = self.alert("a2", refs=("a",))  # NWS re-issue (CON) supersedes "a"
        c = t.update({"a2": a2})
        self.assertEqual([x.id for x in c.updated], ["a2"])
        self.assertFalse(c.new or c.cleared)

        c = t.update({})
        self.assertEqual([x.id for x in c.cleared], ["a2"])

    def test_two_storms(self):
        t = alerts.AlertTracker()
        t.update({"a": self.alert("a")})
        c = t.update({"a": self.alert("a"), "b": self.alert("b")})
        self.assertEqual([x.id for x in c.new], ["b"])


if __name__ == "__main__":
    unittest.main()
