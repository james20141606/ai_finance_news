from datetime import datetime
from zoneinfo import ZoneInfo

from fin_news_digest.digest import run_digest


def _should_run(tz_name: str) -> bool:
    now = datetime.now(ZoneInfo(tz_name))
    return now.hour == 8 and 0 <= now.minute <= 5


def main() -> None:
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
