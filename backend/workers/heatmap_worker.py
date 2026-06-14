"""Heatmap worker — periodic venue snapshots and alert evaluation."""

from __future__ import annotations

import signal
import sys
import time
import uuid
from datetime import datetime, timezone

from loguru import logger

from backend.config import get_settings
from backend.core.alert_engine import evaluate_alerts
from backend.core.heatmap_snapshot import build_heatmap_snapshot
from backend.db import redis_sync
from backend.db.sync_database import (
    count_registered_participants,
    insert_alert,
    insert_heatmap_snapshot,
    load_zone_metadata,
    sync_session,
)


class HeatmapWorker:
    """Periodic snapshot of zone occupancy and energy level."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.interval = self.settings.HEATMAP_SNAPSHOT_INTERVAL
        self._shutdown = False

    def run(self) -> None:
        """Main loop until SIGTERM."""
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        logger.info(f"Heatmap worker started (interval={self.interval}s)")
        while not self._shutdown:
            started = time.monotonic()
            try:
                self._cycle()
            except Exception as exc:
                logger.error(f"Heatmap cycle failed: {exc}")
            elapsed = time.monotonic() - started
            sleep_for = max(0.0, self.interval - elapsed)
            if sleep_for > 0 and not self._shutdown:
                time.sleep(sleep_for)

    def _handle_signal(self, signum: int, _frame: object) -> None:
        logger.info(f"Heatmap worker received signal {signum}, shutting down")
        self._shutdown = True

    def _cycle(self) -> None:
        now = datetime.now(timezone.utc)
        with sync_session() as session:
            zone_meta = load_zone_metadata(session)
            total_registered = count_registered_participants(session)

        raw_occupancy = redis_sync.get_zone_occupancy()
        occupancy = {k: int(v) for k, v in raw_occupancy.items()}
        total_active = redis_sync.count_active_participants(within_seconds=300)

        snapshot = build_heatmap_snapshot(
            occupancy=occupancy,
            zone_metadata=zone_meta,
            total_active=total_active,
            total_registered=total_registered,
            timestamp=now,
        )

        redis_sync.set_heatmap_current(snapshot)
        redis_sync.set_heatmap_heartbeat(now.isoformat(), "running")

        try:
            with sync_session() as session:
                insert_heatmap_snapshot(
                    session,
                    timestamp=now,
                    zone_occupancy=snapshot["zones"],
                    total_active=total_active,
                    energy_level=float(snapshot["energy_level"]),
                )
        except Exception as exc:
            logger.error(f"Heatmap snapshot save failed: {exc}")
            raise

        redis_sync.publish_heatmap_updated()

        zone_summary = ", ".join(
            f"{name}={z['count']}" for name, z in list(snapshot["zones"].items())[:8]
        )
        logger.info(
            f"Heatmap snapshot: active={total_active}, energy={snapshot['energy_level']}, "
            f"zones={{{zone_summary}}}"
        )

        if float(snapshot["energy_level"]) < 0.25:
            logger.warning(
                f"Energy dip: level={snapshot['energy_level']}, threshold=0.25"
            )

        alerts = evaluate_alerts(snapshot, zone_meta)
        for alert in alerts:
            self._persist_alert(alert, now)

    def _persist_alert(self, alert: dict, fired_at: datetime) -> None:
        try:
            with sync_session() as session:
                db_id = insert_alert(
                    session,
                    rule_name=alert["rule_name"],
                    severity=alert["severity"],
                    message=alert["message"],
                    zone=alert.get("zone"),
                    floor=alert.get("floor"),
                    fired_at=fired_at,
                )
                alert["id"] = str(db_id)
        except Exception as exc:
            logger.error(f"Alert persist failed: {exc}")
            return

        redis_sync.push_alert_list(alert)
        redis_sync.publish_alert(alert)
        logger.info(
            f"Alert fired: rule={alert['rule_name']}, zone={alert.get('zone')}, "
            f"severity={alert['severity']}, message={alert['message']}"
        )


def main() -> None:
    """Entry point."""
    worker = HeatmapWorker()
    worker.run()
    sys.exit(0)


if __name__ == "__main__":
    main()
