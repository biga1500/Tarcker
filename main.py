#!/usr/bin/env python3
"""
Tarcker — main entry point.

Usage:
  python main.py              # Start daemon (tracker + scheduler)
  python main.py --summary    # Generate today's summary now and exit
  python main.py --summary yesterday  # Summary for yesterday
  python main.py --config     # Show config file location and exit
"""

import argparse
import logging
import sys
from datetime import date, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("tarcker")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tarcker",
        description="Monitor sua atividade e envia um resumo diário.",
    )
    parser.add_argument(
        "--summary",
        nargs="?",
        const="today",
        metavar="DATE",
        help="Gera o resumo imediatamente. DATE pode ser 'today', 'yesterday' ou YYYY-MM-DD.",
    )
    parser.add_argument(
        "--config",
        action="store_true",
        help="Mostra o caminho do arquivo de configuração.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Ativa logs detalhados.",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    from tarcker.config import load_config, CONFIG_FILE
    config = load_config()

    if args.config:
        print(f"Arquivo de configuração: {CONFIG_FILE}")
        print(f"Banco de dados: {__import__('tarcker.database', fromlist=['get_db_path']).get_db_path()}")
        return

    if args.summary is not None:
        from tarcker import summarizer, notifier

        day_arg = args.summary
        if day_arg == "today":
            day = date.today()
        elif day_arg == "yesterday":
            day = date.today() - timedelta(days=1)
        else:
            try:
                day = date.fromisoformat(day_arg)
            except ValueError:
                print(f"Formato de data inválido: {day_arg}. Use YYYY-MM-DD.")
                sys.exit(1)

        summary = summarizer.build_summary(day)
        text_report = summarizer.render_text(summary)
        print(text_report)

        if config.get("html_report", {}).get("enabled", True):
            path = summarizer.save_html_report(summary)
            print(f"\nRelatório HTML salvo em: {path}")

        notifier.notify(summary, text_report, summarizer.render_html(summary), config)
        return

    # --- Normal daemon mode ---
    from tarcker.tracker import ActivityTracker
    from tarcker.scheduler import DailySummaryScheduler

    logger.info("Tarcker iniciado. Pressione Ctrl+C para parar.")
    scheduler = DailySummaryScheduler(config)
    scheduler.start()

    tracker = ActivityTracker()
    try:
        tracker.run()
    except KeyboardInterrupt:
        logger.info("Tarcker encerrado.")


if __name__ == "__main__":
    main()
