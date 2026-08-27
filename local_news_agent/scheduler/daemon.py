from __future__ import annotations

import time
import sys
from datetime import datetime, timezone
from collections.abc import Callable


def run_forever(run_cycle: Callable[[], object], every_minutes: int) -> None:
    while True:
        try:
            run_cycle()
        except Exception as exc:
            print(f"{datetime.now(timezone.utc).isoformat()} cycle_failed {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        time.sleep(max(1,every_minutes)*60)

