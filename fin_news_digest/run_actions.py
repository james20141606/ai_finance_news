from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import os
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fin_news_digest.digest import run_digest


_WINDOW_MINUTES = 20


def _should_run(tz_name: str) -> bool:
    now = datetime.now(ZoneInfo(tz_name))
    return now.hour == 8 and 0 <= now.minute <= _WINDOW_MINUTES


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def main() -> None:
    if _truthy(os.getenv("FORCE_SEND", "")):
        print("FORCE_SEND enabled: sending both editions.")
        run_digest("NY 08:00")
        run_digest("BJ 08:00")
        return

    if _truthy(os.getenv("SCHEDULED_RUN", "")):
        print("SCHEDULED_RUN enabled: sending scheduled editions.")
        # Send both editions on schedule to avoid delay skips
        run_digest("NY 08:00")
        run_digest("BJ 08:00")
        return

    ran = False
    if _should_run("America/New_York"):
        run_digest("NY 08:00")
        ran = True
    if _should_run("Asia/Shanghai"):
        run_digest("BJ 08:00")
        ran = True
    if not ran:
        print("No matching schedule window. Skipping.")


if __name__ == "__main__":
    main()
