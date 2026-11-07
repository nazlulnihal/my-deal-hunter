"""
Standalone Persistent Background Worker Daemon (`python3 -m app.worker`).
Operates completely independently of the web UI or FastAPI server so that
wishlist monitoring, deal sniping, and Telegram alerts continue 24/7.
"""

import os
import sys
import time
from datetime import datetime, timezone
from .orchestrator import PlatformOrchestrator


def run_daemon(max_cycles: int = 0, sleep_seconds: int = 60) -> None:
    orchestrator = PlatformOrchestrator()
    cycle = 0
    print(f"[SniperWorker] Started autonomous monitoring daemon at {datetime.now(timezone.utc).isoformat()}")
    while True:
        cycle += 1
        res = orchestrator.run_background_worker_cycle()
        print(f"[SniperWorker] Cycle #{cycle} completed at {res['cycle_completed_at']} ({len(res['jobs_updated'])} jobs updated)")
        if 0 < max_cycles <= cycle:
            break
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    cycles_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    run_daemon(max_cycles=cycles_arg, sleep_seconds=1)
