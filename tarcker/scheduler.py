"""
Background thread that fires the daily summary at a configured time.
"""

import logging
import threading
import time
from datetime import date, datetime

logger = logging.getLogger(__name__)


def _run_summary(config: dict) -> None:
    """Build and dispatch the daily summary."""
    from tarcker import summarizer, notifier

    yesterday = date.today()  # called at end of day / midnight, so today IS the day
    logger.info("Generating daily summary for %s", yesterday)

    summary = summarizer.build_summary(yesterday)
    text_report = summarizer.render_text(summary)

    html_path = None
    html_body = None
    if config.get("html_report", {}).get("enabled", True):
        html_path = summarizer.save_html_report(summary)
        html_body = summarizer.render_html(summary)
        logger.info("HTML report saved to %s", html_path)

    print("\n" + text_report + "\n")
    notifier.notify(summary, text_report, html_body, config)


class DailySummaryScheduler(threading.Thread):
    """Daemon thread that wakes up at the configured summary_time and triggers the report."""

    def __init__(self, config: dict):
        super().__init__(daemon=True, name="tarcker-scheduler")
        self.config = config

    def run(self) -> None:
        summary_time = self.config.get("summary_time", "18:00")
        hour, minute = map(int, summary_time.split(":"))
        logger.info("Daily summary scheduled for %02d:%02d", hour, minute)

        while True:
            now = datetime.now()
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                # Already past today's time; schedule for tomorrow
                from datetime import timedelta
                target += timedelta(days=1)

            wait_s = (target - now).total_seconds()
            logger.debug("Next summary in %.0f seconds (%s)", wait_s, target.strftime("%H:%M"))
            time.sleep(wait_s)
            _run_summary(self.config)
