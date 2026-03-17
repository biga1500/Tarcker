"""
Configuration management for Tarcker.
Settings are loaded from ~/.tarcker/config.json (created on first run).
"""

import json
import os
from pathlib import Path

DEFAULT_CONFIG = {
    # How often to poll the active window (seconds)
    "poll_interval": 5,

    # Idle threshold: user is considered idle after this many seconds of inactivity
    "idle_threshold": 120,

    # Time to send the daily summary (24h format)
    "summary_time": "18:00",

    # Email settings (leave empty to disable email)
    "email": {
        "enabled": False,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "use_tls": True,
        "username": "",
        "password": "",
        "from_addr": "",
        "to_addr": ""
    },

    # Desktop notification settings
    "desktop_notification": {
        "enabled": True
    },

    # Save HTML report to disk
    "html_report": {
        "enabled": True,
        "output_dir": "~/.tarcker/reports"
    },

    # App categories: map substrings (lowercase) to category names
    "categories": {
        "code": ["code", "vscode", "vim", "neovim", "pycharm", "intellij",
                 "sublime", "atom", "emacs", "terminal", "konsole", "gnome-terminal",
                 "xterm", "bash", "zsh", "fish", "ssh"],
        "browser": ["firefox", "chrome", "chromium", "brave", "opera", "safari",
                    "edge", "vivaldi"],
        "communication": ["slack", "discord", "telegram", "whatsapp", "signal",
                          "zoom", "teams", "meet", "skype", "thunderbird"],
        "productivity": ["libreoffice", "word", "excel", "powerpoint", "notion",
                         "obsidian", "evernote", "trello", "jira"],
        "entertainment": ["spotify", "vlc", "mpv", "netflix", "youtube", "twitch",
                          "steam", "games"],
        "design": ["figma", "gimp", "inkscape", "blender", "photoshop", "illustrator"],
        "system": ["nautilus", "dolphin", "thunar", "files", "settings", "system-monitor"]
    }
}

CONFIG_DIR = Path.home() / ".tarcker"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> dict:
    """Load config from disk, creating defaults if not present."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    with open(CONFIG_FILE) as f:
        on_disk = json.load(f)
    # Merge with defaults so new keys are always present
    merged = _deep_merge(DEFAULT_CONFIG, on_disk)
    return merged


def save_config(config: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
