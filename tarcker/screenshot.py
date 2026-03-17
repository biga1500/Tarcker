"""
Periodic screenshot capture using Pillow (ImageGrab).

Screenshots are saved as compressed JPEGs in ~/.tarcker/screenshots/YYYY-MM-DD/
and their paths are stored in the database.

Config keys used:
  screenshots.enabled        (bool, default True)
  screenshots.interval_s     (int, default 300 = 5 min)
  screenshots.quality        (int 1-95, default 60)
  screenshots.max_width      (int, default 1920  — resizes wider screens)
"""

import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ScreenshotCapture(threading.Thread):
    """Daemon thread that takes a screenshot every N seconds."""

    def __init__(self, config: dict) -> None:
        super().__init__(daemon=True, name="tarcker-screenshots")
        self._cfg = config.get("screenshots", {})
        self._interval = int(self._cfg.get("interval_s", 300))
        self._quality  = int(self._cfg.get("quality", 60))
        self._max_w    = int(self._cfg.get("max_width", 1920))
        self._base_dir = Path(
            config.get("html_report", {}).get("output_dir", "~/.tarcker/reports")
        ).expanduser().parent / "screenshots"

    def _capture(self) -> Optional[Path]:
        try:
            from PIL import ImageGrab
        except ImportError:
            logger.error("Pillow not installed. Run: pip install Pillow")
            return None

        try:
            img = ImageGrab.grab(all_screens=True)
        except Exception:
            # all_screens not supported on all platforms
            try:
                from PIL import ImageGrab as IG
                img = IG.grab()
            except Exception as exc:
                logger.warning("Screenshot failed: %s", exc)
                return None

        # Resize if wider than max_width
        if img.width > self._max_w:
            ratio = self._max_w / img.width
            img = img.resize(
                (self._max_w, int(img.height * ratio)),
                resample=1,  # LANCZOS
            )

        now = datetime.now()
        day_dir = self._base_dir / now.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        path = day_dir / f"{now.strftime('%H-%M-%S')}.jpg"

        img.convert("RGB").save(str(path), "JPEG", quality=self._quality, optimize=True)
        return path

    def run(self) -> None:
        from tarcker import database
        from tarcker.tracker import get_active_window

        logger.info("Screenshot capture started (every %ds)", self._interval)
        while True:
            time.sleep(self._interval)
            path = self._capture()
            if path:
                app, title = get_active_window()
                database.insert_screenshot(datetime.now(), str(path), app, title)
                from tarcker import live_log
                live_log.log_screenshot(str(path), app)
                logger.debug("Screenshot saved: %s", path)
