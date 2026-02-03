from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

from fin_news_digest.digest import run_digest


def main() -> None:
    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_digest,
        CronTrigger(hour=8, minute=0, timezone=ZoneInfo("America/New_York")),
        kwargs={"edition_label": "NY 08:00"},
        id="ny_0800",
    )
    scheduler.add_job(
        run_digest,
        CronTrigger(hour=8, minute=0, timezone=ZoneInfo("Asia/Shanghai")),
        kwargs={"edition_label": "BJ 08:00"},
        id="bj_0800",
    )
    scheduler.start()


if __name__ == "__main__":
    main()
