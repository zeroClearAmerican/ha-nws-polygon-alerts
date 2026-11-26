"""Pure-Python alert parsing, polygon matching and change tracking.

Nothing in this module imports Home Assistant, so it can be tested standalone.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------- geometry

Ring = Sequence[Sequence[float]]  # [[lon, lat], ...]


def _point_in_ring(lon: float, lat: float, ring: Ring) -> bool:
    """Ray-casting point-in-polygon test for a single linear ring."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_cross:
                inside = not inside
        j = i
    return inside


def _point_in_polygon_coords(lon: float, lat: float, rings: Sequence[Ring]) -> bool:
    """GeoJSON Polygon coordinates: first ring is the outer edge, rest are holes."""
    if not rings or not _point_in_ring(lon, lat, rings[0]):
        return False
    return not any(_point_in_ring(lon, lat, hole) for hole in rings[1:])


def point_in_geometry(lat: float, lon: float, geometry: dict[str, Any] | None) -> bool:
    """Return True if (lat, lon) falls inside a GeoJSON Polygon/MultiPolygon."""
    if not geometry:
        return False
    gtype = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if gtype == "Polygon":
        return _point_in_polygon_coords(lon, lat, coords)
    if gtype == "MultiPolygon":
        return any(_point_in_polygon_coords(lon, lat, poly) for poly in coords)
    if gtype == "GeometryCollection":
        return any(
            point_in_geometry(lat, lon, g) for g in geometry.get("geometries") or []
        )
    return False


# ---------------------------------------------------------------- parsing


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class Alert:
    """One NWS alert relevant to a location."""

    id: str
    event: str
    headline: str
    description: str
    instruction: str
    severity: str
    certainty: str
    urgency: str
    area: str
    sender: str
    message_type: str
    sent: datetime | None
    effective: datetime | None
    expires: datetime | None
    ends: datetime | None
    references: tuple[str, ...]
    has_polygon: bool
    url: str

    @classmethod
    def from_feature(cls, feature: dict[str, Any]) -> Alert:
        p = feature.get("properties") or {}
        geometry = feature.get("geometry")
        return cls(
            id=p.get("id") or feature.get("id") or "",
            event=p.get("event") or "",
            headline=p.get("headline") or "",
            description=p.get("description") or "",
            instruction=p.get("instruction") or "",
            severity=p.get("severity") or "",
            certainty=p.get("certainty") or "",
            urgency=p.get("urgency") or "",
            area=p.get("areaDesc") or "",
            sender=p.get("senderName") or "",
            message_type=p.get("messageType") or "",
            sent=_parse_dt(p.get("sent")),
            effective=_parse_dt(p.get("effective")),
            expires=_parse_dt(p.get("expires")),
            ends=_parse_dt(p.get("ends")),
            references=tuple(
                r.get("identifier", "")
                for r in p.get("references") or []
                if isinstance(r, dict)
            ),
            has_polygon=bool(geometry),
            url=feature.get("id") or p.get("@id") or "",
        )

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Alert:
        """Inverse of as_dict() (used to restore state after a restart)."""
        return cls(
            id=d["id"],
            event=d.get("event", ""),
            headline=d.get("headline", ""),
            description=d.get("description", ""),
            instruction=d.get("instruction", ""),
            severity=d.get("severity", ""),
            certainty=d.get("certainty", ""),
            urgency=d.get("urgency", ""),
            area=d.get("area", ""),
            sender=d.get("sender", ""),
            message_type=d.get("message_type", ""),
            sent=_parse_dt(d.get("sent")),
            effective=_parse_dt(d.get("effective")),
            expires=_parse_dt(d.get("expires")),
            ends=_parse_dt(d.get("ends")),
            references=tuple(d.get("references") or ()),
            has_polygon=bool(d.get("has_polygon")),
            url=d.get("url", ""),
        )

    @property
    def end_time(self) -> datetime | None:
        return self.ends or self.expires

    def is_expired(self, now: datetime) -> bool:
        end = self.end_time
        return end is not None and end <= now

    def as_dict(self) -> dict[str, Any]:
        """Flat, JSON-safe representation (attributes, events, templates)."""

        def iso(d: datetime | None) -> str | None:
            return d.isoformat() if d else None

        return {
            "id": self.id,
            "event": self.event,
            "headline": self.headline,
            "description": self.description,
            "instruction": self.instruction,
            "severity": self.severity,
            "certainty": self.certainty,
            "urgency": self.urgency,
            "area": self.area,
            "sender": self.sender,
            "message_type": self.message_type,
            "sent": iso(self.sent),
            "effective": iso(self.effective),
            "expires": iso(self.expires),
            "ends": iso(self.ends),
            "has_polygon": self.has_polygon,
            "references": list(self.references),
            "url": self.url,
        }


def match_alerts(
    features: Iterable[dict[str, Any]],
    lat: float,
    lon: float,
    events: set[str],
    include_zone_alerts: bool,
    now: datetime | None = None,
) -> dict[str, Alert]:
    """Filter raw GeoJSON features down to alerts that cover the point.

    Alerts with a polygon must contain the point. Alerts without a polygon
    (zone/county based, e.g. watches) only match if include_zone_alerts is set;
    the API's ?point= query already limited those to zones containing the point.
    """
    now = now or datetime.now(timezone.utc)
    matched: dict[str, Alert] = {}
    for feature in features:
        props = feature.get("properties") or {}
        if props.get("event") not in events:
            continue
        if props.get("messageType") == "Cancel":
            continue
        if (props.get("status") or "Actual") != "Actual":
            continue
        geometry = feature.get("geometry")
        if geometry:
            if not point_in_geometry(lat, lon, geometry):
                continue
        elif not include_zone_alerts:
            continue
        alert = Alert.from_feature(feature)
        if not alert.id or alert.is_expired(now):
            continue
        matched[alert.id] = alert
    return matched


# ---------------------------------------------------------------- tracking


@dataclass
class AlertChanges:
    new: list[Alert] = field(default_factory=list)
    updated: list[Alert] = field(default_factory=list)
    cleared: list[Alert] = field(default_factory=list)


class AlertTracker:
    """Diffs successive sets of matched alerts.

    NWS re-issues a warning with a new id when it's updated (CON/EXT/etc.), and
    lists the old ids in `references`. Those are reported as "updated" rather
    than "new" so you don't get a second tornado alarm for the same storm.
    """

    def __init__(self) -> None:
        self.active: dict[str, Alert] = {}

    def update(self, current: dict[str, Alert]) -> AlertChanges:
        changes = AlertChanges()
        superseded: set[str] = set()

        for alert_id, alert in current.items():
            if alert_id in self.active:
                continue
            replaced = [r for r in alert.references if r in self.active]
            if replaced:
                superseded.update(replaced)
                changes.updated.append(alert)
            else:
                changes.new.append(alert)

        for alert_id, alert in self.active.items():
            if alert_id not in current and alert_id not in superseded:
                changes.cleared.append(alert)

        self.active = dict(current)
        return changes
