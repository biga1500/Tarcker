"""
Generates daily activity summaries in plain-text and HTML formats.
"""

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

from tarcker import database
from tarcker.config import load_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CATEGORY_EMOJI = {
    "code":          "💻",
    "browser":       "🌐",
    "communication": "💬",
    "productivity":  "📝",
    "entertainment": "🎵",
    "design":        "🎨",
    "system":        "⚙️",
    "other":         "📦",
}


def _fmt_duration(seconds: float) -> str:
    """Convert seconds to human-readable string, e.g. '2h 34m'."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    h, m = divmod(minutes, 60)
    return f"{h}h {m}m" if m else f"{h}h"


def _pct(part: float, total: float) -> str:
    if total == 0:
        return "0%"
    return f"{part / total * 100:.0f}%"


# ---------------------------------------------------------------------------
# Summary data structure
# ---------------------------------------------------------------------------

def build_summary(day: Optional[date] = None) -> dict:
    """Collect all data for a given day and return a structured summary dict."""
    if day is None:
        day = date.today()

    config = load_config()
    app_totals = database.get_app_totals_for_date(day)
    cat_totals = database.get_category_totals_for_date(day)
    idle_rows = database.get_idle_for_date(day)
    sessions = database.get_sessions_for_date(day)

    active_s = sum(r["total_s"] for r in app_totals)
    idle_s = sum(r["duration_s"] for r in idle_rows)
    total_s = active_s + idle_s

    # First/last activity
    first_seen = None
    last_seen = None
    if sessions:
        first_seen = datetime.fromisoformat(sessions[0]["started_at"])
        last_seen = datetime.fromisoformat(sessions[-1]["ended_at"] or sessions[-1]["started_at"])

    # Top apps (limit 10)
    top_apps = app_totals[:10]

    # Hourly breakdown
    hourly: dict = {h: 0.0 for h in range(24)}
    for s in sessions:
        started = datetime.fromisoformat(s["started_at"])
        hourly[started.hour] += s["duration_s"]

    return {
        "day": day,
        "active_s": active_s,
        "idle_s": idle_s,
        "total_s": total_s,
        "first_seen": first_seen,
        "last_seen": last_seen,
        "top_apps": top_apps,
        "cat_totals": cat_totals,
        "hourly": hourly,
        "session_count": len(sessions),
    }


# ---------------------------------------------------------------------------
# Plain-text report
# ---------------------------------------------------------------------------

def render_text(summary: dict) -> str:
    day = summary["day"]
    lines = [
        f"╔{'═' * 54}╗",
        f"║{'TARCKER — RESUMO DO DIA':^54}║",
        f"║{day.strftime('%A, %d de %B de %Y'):^54}║",
        f"╚{'═' * 54}╝",
        "",
    ]

    # Overview
    lines += [
        "📊 VISÃO GERAL",
        f"  Tempo ativo:   {_fmt_duration(summary['active_s'])}",
        f"  Tempo ocioso:  {_fmt_duration(summary['idle_s'])}",
        f"  Total rastreado: {_fmt_duration(summary['total_s'])}",
    ]
    if summary["first_seen"] and summary["last_seen"]:
        lines += [
            f"  Início:        {summary['first_seen'].strftime('%H:%M')}",
            f"  Fim:           {summary['last_seen'].strftime('%H:%M')}",
        ]
    lines.append("")

    # Categories
    if summary["cat_totals"]:
        lines.append("🗂️  CATEGORIAS")
        for c in summary["cat_totals"]:
            emoji = CATEGORY_EMOJI.get(c["category"], "📦")
            bar_len = int(c["total_s"] / max(summary["active_s"], 1) * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            lines.append(
                f"  {emoji} {c['category']:<14} {bar}  {_fmt_duration(c['total_s'])} "
                f"({_pct(c['total_s'], summary['active_s'])})"
            )
        lines.append("")

    # Top apps
    if summary["top_apps"]:
        lines.append("🏆 TOP APLICATIVOS")
        for i, app in enumerate(summary["top_apps"], 1):
            lines.append(
                f"  {i:2}. {app['app_name']:<25} {_fmt_duration(app['total_s']):<10} "
                f"({_pct(app['total_s'], summary['active_s'])})"
            )
        lines.append("")

    # Hourly chart (only hours with activity)
    active_hours = {h: v for h, v in summary["hourly"].items() if v > 0}
    if active_hours:
        lines.append("⏰ ATIVIDADE POR HORA")
        max_val = max(active_hours.values())
        for h in sorted(active_hours):
            bar_len = int(active_hours[h] / max_val * 30)
            bar = "▓" * bar_len
            lines.append(f"  {h:02d}h  {bar:<30}  {_fmt_duration(active_hours[h])}")
        lines.append("")

    lines.append(f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} pelo Tarcker")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

def render_html(summary: dict) -> str:
    day = summary["day"]
    config = load_config()

    # Build category rows
    cat_rows = ""
    for c in summary["cat_totals"]:
        emoji = CATEGORY_EMOJI.get(c["category"], "📦")
        pct = c["total_s"] / max(summary["active_s"], 1) * 100
        cat_rows += f"""
        <tr>
          <td>{emoji} {c['category'].capitalize()}</td>
          <td>
            <div class="bar-wrap">
              <div class="bar" style="width:{pct:.0f}%"></div>
            </div>
          </td>
          <td class="right">{_fmt_duration(c['total_s'])}</td>
          <td class="right">{pct:.0f}%</td>
        </tr>"""

    # Build app rows
    app_rows = ""
    for i, app in enumerate(summary["top_apps"], 1):
        pct = app["total_s"] / max(summary["active_s"], 1) * 100
        emoji = CATEGORY_EMOJI.get(app["category"], "📦")
        app_rows += f"""
        <tr>
          <td class="rank">{i}</td>
          <td>{emoji} {app['app_name']}</td>
          <td class="right">{_fmt_duration(app['total_s'])}</td>
          <td class="right">{pct:.0f}%</td>
        </tr>"""

    # Hourly bars
    max_hourly = max(summary["hourly"].values()) if any(summary["hourly"].values()) else 1
    hourly_bars = ""
    for h in range(24):
        val = summary["hourly"][h]
        pct = val / max_hourly * 100
        hourly_bars += f"""
        <div class="hour-col">
          <div class="hour-bar-wrap">
            <div class="hour-bar" style="height:{pct:.0f}%"
                 title="{h:02d}h — {_fmt_duration(val)}"></div>
          </div>
          <div class="hour-label">{h:02d}</div>
        </div>"""

    first = summary["first_seen"].strftime("%H:%M") if summary["first_seen"] else "—"
    last = summary["last_seen"].strftime("%H:%M") if summary["last_seen"] else "—"

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Tarcker — {day.strftime('%d/%m/%Y')}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0f1117; color: #e2e8f0; padding: 2rem; }}
    h1 {{ font-size: 1.8rem; margin-bottom: .25rem; color: #f8fafc; }}
    .subtitle {{ color: #94a3b8; margin-bottom: 2rem; font-size: .95rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
             gap: 1rem; margin-bottom: 2rem; }}
    .card {{ background: #1e2130; border-radius: 12px; padding: 1.25rem;
             border: 1px solid #2d3148; }}
    .card .label {{ font-size: .8rem; color: #94a3b8; margin-bottom: .35rem; text-transform: uppercase; }}
    .card .value {{ font-size: 1.6rem; font-weight: 700; color: #f8fafc; }}
    section {{ background: #1e2130; border-radius: 12px; padding: 1.5rem;
               border: 1px solid #2d3148; margin-bottom: 1.5rem; }}
    section h2 {{ font-size: 1rem; color: #94a3b8; margin-bottom: 1rem;
                  text-transform: uppercase; letter-spacing: .05em; }}
    table {{ width: 100%; border-collapse: collapse; }}
    td, th {{ padding: .5rem .75rem; text-align: left; font-size: .9rem; }}
    tr:not(:last-child) td {{ border-bottom: 1px solid #2d3148; }}
    .right {{ text-align: right; }}
    .rank {{ color: #64748b; width: 2rem; }}
    .bar-wrap {{ background: #2d3148; border-radius: 4px; height: 8px; min-width: 120px; }}
    .bar {{ background: linear-gradient(90deg, #6366f1, #a78bfa); height: 8px; border-radius: 4px; }}
    .hourly {{ display: flex; align-items: flex-end; gap: 3px; height: 100px; }}
    .hour-col {{ display: flex; flex-direction: column; align-items: center; flex: 1; }}
    .hour-bar-wrap {{ flex: 1; display: flex; align-items: flex-end; width: 100%; }}
    .hour-bar {{ background: linear-gradient(180deg, #6366f1, #818cf8);
                 width: 100%; border-radius: 3px 3px 0 0; min-height: 2px; transition: height .3s; }}
    .hour-label {{ font-size: .6rem; color: #475569; margin-top: 4px; }}
    footer {{ text-align: center; color: #475569; font-size: .8rem; margin-top: 2rem; }}
  </style>
</head>
<body>
  <h1>📊 Tarcker</h1>
  <p class="subtitle">Resumo do dia — {day.strftime('%A, %d de %B de %Y')}</p>

  <div class="grid">
    <div class="card"><div class="label">Tempo Ativo</div>
      <div class="value">{_fmt_duration(summary['active_s'])}</div></div>
    <div class="card"><div class="label">Tempo Ocioso</div>
      <div class="value">{_fmt_duration(summary['idle_s'])}</div></div>
    <div class="card"><div class="label">Total Rastreado</div>
      <div class="value">{_fmt_duration(summary['total_s'])}</div></div>
    <div class="card"><div class="label">Apps Usados</div>
      <div class="value">{len(summary['top_apps'])}</div></div>
    <div class="card"><div class="label">Início / Fim</div>
      <div class="value" style="font-size:1.1rem">{first} – {last}</div></div>
  </div>

  <section>
    <h2>Categorias</h2>
    <table>{cat_rows}</table>
  </section>

  <section>
    <h2>Top Aplicativos</h2>
    <table>
      <tr><th></th><th>App</th><th class="right">Tempo</th><th class="right">%</th></tr>
      {app_rows}
    </table>
  </section>

  <section>
    <h2>Atividade por Hora</h2>
    <div class="hourly">{hourly_bars}</div>
  </section>

  <footer>Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} pelo Tarcker</footer>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Save report to disk
# ---------------------------------------------------------------------------

def save_html_report(summary: dict) -> Path:
    config = load_config()
    output_dir = Path(config["html_report"]["output_dir"]).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"tarcker_{summary['day'].isoformat()}.html"
    path.write_text(render_html(summary), encoding="utf-8")
    return path
