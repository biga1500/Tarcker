#!/usr/bin/env python3
"""
Tarcker — main entry point.

Usage:
  python main.py              # Start daemon (all capture modules + live log)
  python main.py --summary    # Generate today's summary now and exit
  python main.py --summary yesterday
  python main.py --summary 2026-03-15
  python main.py --config     # Show config/DB paths and exit
  python main.py --no-log     # Run daemon silently (no live feed)
"""

import argparse
import logging
import sys
from datetime import date, timedelta

# Show INFO+ from tarcker, suppress chatty third-party libs
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("tarcker").setLevel(logging.INFO)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tarcker",
        description="Monitor sua atividade e envia um resumo diário.",
    )
    parser.add_argument(
        "--summary", nargs="?", const="today", metavar="DATE",
        help="Gera o resumo. DATE: 'today', 'yesterday' ou YYYY-MM-DD.",
    )
    parser.add_argument(
        "--config", action="store_true",
        help="Mostra caminhos de configuração e banco de dados.",
    )
    parser.add_argument(
        "--no-log", action="store_true",
        help="Desativa o log ao vivo no terminal.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Ativa logs de depuração.",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger("tarcker").setLevel(logging.DEBUG)

    from tarcker.config import load_config, CONFIG_FILE
    from tarcker import database
    config = load_config()
    database.init_db()

    # ------------------------------------------------------------------
    # --config
    # ------------------------------------------------------------------
    if args.config:
        print(f"Configuração : {CONFIG_FILE}")
        print(f"Banco de dados: {database.get_db_path()}")
        from pathlib import Path
        reports = Path(config["html_report"]["output_dir"]).expanduser()
        screenshots = reports.parent / "screenshots"
        print(f"Relatórios  : {reports}")
        print(f"Screenshots : {screenshots}")
        return

    # ------------------------------------------------------------------
    # --summary
    # ------------------------------------------------------------------
    if args.summary is not None:
        from tarcker import summarizer, notifier

        if args.summary == "today":
            day = date.today()
        elif args.summary == "yesterday":
            day = date.today() - timedelta(days=1)
        else:
            try:
                day = date.fromisoformat(args.summary)
            except ValueError:
                print(f"Formato de data inválido: {args.summary}. Use YYYY-MM-DD.")
                sys.exit(1)

        summary = summarizer.build_summary(day)
        text_report = summarizer.render_text(summary)
        print(text_report)

        if config.get("html_report", {}).get("enabled", True):
            path = summarizer.save_html_report(summary)
            print(f"\nRelatório HTML: {path}")

        notifier.notify(summary, text_report, summarizer.render_html(summary), config)
        return

    # ------------------------------------------------------------------
    # Daemon mode: start all capture threads
    # ------------------------------------------------------------------
    from tarcker.tracker import ActivityTracker
    from tarcker.scheduler import DailySummaryScheduler
    from tarcker.keylogger import KeyLogger
    from tarcker.screenshot import ScreenshotCapture
    from tarcker.browser_history import BrowserHistorySync
    from tarcker.live_log import LiveLogRenderer

    # Override live_log if --no-log passed
    if args.no_log:
        config.setdefault("live_log", {})["enabled"] = False

    # Start live log renderer first so it catches everything
    live_log_thread = LiveLogRenderer(config)
    live_log_thread.start()

    # Keylogger
    keylogger = KeyLogger()
    keylogger.start()

    # Screenshot capture
    if config.get("screenshots", {}).get("enabled", True):
        ScreenshotCapture(config).start()

    # Browser history sync
    BrowserHistorySync(config).start()

    # Daily summary scheduler
    DailySummaryScheduler(config).start()

    # Main tracker loop (blocking)
    tracker = ActivityTracker()
    try:
        tracker.run()
    except KeyboardInterrupt:
        print("\nTarcker encerrado.")


if __name__ == "__main__":
    main()
