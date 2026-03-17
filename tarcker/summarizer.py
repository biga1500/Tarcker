"""
Generates daily activity summaries combining all data sources:
  - Window focus sessions (time per app/category)
  - Keylog (typing volume, top windows, reconstructed text snippets)
  - Screenshots (timeline, count)
  - Browser history (URLs visited, top domains, top titles)
"""

import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

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


def _domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lstrip("www.")
        return host or url[:40]
    except Exception:
        return url[:40]


def _top_domains(visits) -> List[dict]:
    counts: dict = {}
    for v in visits:
        d = _domain(v["url"])
        counts[d] = counts.get(d, 0) + 1
    return sorted(
        [{"domain": k, "count": v} for k, v in counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )[:15]


def _extract_searches(visits) -> List[str]:
    """Extract search queries from Google/Bing/DuckDuckGo URLs."""
    queries = []
    patterns = [
        re.compile(r"[?&]q=([^&]+)"),   # Google, Bing, DDG
        re.compile(r"[?&]query=([^&]+)"),
        re.compile(r"[?&]text=([^&]+)"),  # Yandex
    ]
    for v in visits:
        url = v["url"]
        for p in patterns:
            m = p.search(url)
            if m:
                from urllib.parse import unquote_plus
                queries.append(unquote_plus(m.group(1)))
                break
    return queries


# ---------------------------------------------------------------------------
# Build summary dict
# ---------------------------------------------------------------------------

def build_summary(day: Optional[date] = None) -> dict:
    if day is None:
        day = date.today()

    config = load_config()
    app_totals  = database.get_app_totals_for_date(day)
    cat_totals  = database.get_category_totals_for_date(day)
    idle_rows   = database.get_idle_for_date(day)
    sessions    = database.get_sessions_for_date(day)
    keylog_rows = database.get_keylog_for_date(day)
    screenshots = database.get_screenshots_for_date(day)
    visits      = database.get_browser_visits_for_date(day)

    active_s = sum(r["total_s"] for r in app_totals)
    idle_s   = sum(r["duration_s"] for r in idle_rows)

    first_seen = last_seen = None
    if sessions:
        first_seen = datetime.fromisoformat(sessions[0]["started_at"])
        last_seen  = datetime.fromisoformat(
            sessions[-1]["ended_at"] or sessions[-1]["started_at"]
        )

    # Hourly active breakdown
    hourly: dict = {h: 0.0 for h in range(24)}
    for s in sessions:
        hourly[datetime.fromisoformat(s["started_at"]).hour] += s["duration_s"]

    # Keylog stats
    total_chars    = sum(r["char_count"] for r in keylog_rows)
    total_keystrokes = total_chars  # char_count already includes special keys
    # Top windows by typing volume
    kl_windows: dict = {}
    for r in keylog_rows:
        key = r["app_name"]
        kl_windows[key] = kl_windows.get(key, 0) + r["char_count"]
    top_typing_apps = sorted(
        [{"app": k, "chars": v} for k, v in kl_windows.items()],
        key=lambda x: x["chars"], reverse=True
    )[:5]

    # Recent keylog snippets (last 10 non-empty bursts, trimmed)
    snippets = []
    for r in reversed(keylog_rows[-20:]):
        text = r["text"].strip()
        if text and text != "***" and len(text) > 3:
            snippets.append({
                "time":  r["timestamp"][11:16],
                "app":   r["app_name"],
                "title": r["window_title"][:60],
                "text":  text[:200],
            })
        if len(snippets) >= 10:
            break
    snippets.reverse()

    # Browser stats
    top_domains  = _top_domains(visits)
    search_queries = _extract_searches(visits)

    return {
        "day":            day,
        "active_s":       active_s,
        "idle_s":         idle_s,
        "total_s":        active_s + idle_s,
        "first_seen":     first_seen,
        "last_seen":      last_seen,
        "top_apps":       app_totals[:10],
        "cat_totals":     cat_totals,
        "hourly":         hourly,
        "session_count":  len(sessions),
        # keylog
        "total_chars":    total_chars,
        "top_typing_apps": top_typing_apps,
        "keylog_snippets": snippets,
        # screenshots
        "screenshot_count": len(screenshots),
        "screenshots":    [dict(s) for s in screenshots],
        # browser
        "browser_visits": len(visits),
        "top_domains":    top_domains,
        "search_queries": search_queries[:20],
        "visits":         [dict(v) for v in visits],
    }


# ---------------------------------------------------------------------------
# Plain-text report
# ---------------------------------------------------------------------------

def render_text(summary: dict) -> str:
    day = summary["day"]
    lines = [
        f"╔{'═' * 60}╗",
        f"║{'TARCKER — RESUMO DO DIA':^60}║",
        f"║{day.strftime('%A, %d de %B de %Y'):^60}║",
        f"╚{'═' * 60}╝",
        "",
    ]

    first = summary["first_seen"].strftime("%H:%M") if summary["first_seen"] else "—"
    last  = summary["last_seen"].strftime("%H:%M") if summary["last_seen"] else "—"

    lines += [
        "📊 VISÃO GERAL",
        f"  Tempo ativo:       {_fmt_duration(summary['active_s'])}",
        f"  Tempo ocioso:      {_fmt_duration(summary['idle_s'])}",
        f"  Início / Fim:      {first} – {last}",
        f"  Teclas digitadas:  {summary['total_chars']:,}",
        f"  Sites visitados:   {summary['browser_visits']}",
        f"  Screenshots:       {summary['screenshot_count']}",
        "",
    ]

    # Categories
    if summary["cat_totals"]:
        lines.append("🗂️  CATEGORIAS")
        for c in summary["cat_totals"]:
            emoji = CATEGORY_EMOJI.get(c["category"], "📦")
            bar_len = int(c["total_s"] / max(summary["active_s"], 1) * 24)
            bar = "█" * bar_len + "░" * (24 - bar_len)
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
                f"  {i:2}. {app['app_name']:<28} {_fmt_duration(app['total_s']):<10}"
                f" ({_pct(app['total_s'], summary['active_s'])})"
            )
        lines.append("")

    # Typing
    if summary["top_typing_apps"]:
        lines.append("⌨️  MAIS DIGITADO EM")
        for a in summary["top_typing_apps"]:
            lines.append(f"  {a['app']:<30} {a['chars']:,} chars")
        lines.append("")

    # Browser
    if summary["top_domains"]:
        lines.append("🌐 TOP SITES")
        for d in summary["top_domains"][:10]:
            lines.append(f"  {d['domain']:<40} {d['count']} visitas")
        lines.append("")

    if summary["search_queries"]:
        lines.append("🔍 BUSCAS REALIZADAS")
        for q in summary["search_queries"][:15]:
            lines.append(f"  • {q}")
        lines.append("")

    # Hourly chart
    active_hours = {h: v for h, v in summary["hourly"].items() if v > 0}
    if active_hours:
        lines.append("⏰ ATIVIDADE POR HORA")
        max_val = max(active_hours.values())
        for h in sorted(active_hours):
            bar_len = int(active_hours[h] / max_val * 32)
            lines.append(f"  {h:02d}h  {'▓' * bar_len:<32}  {_fmt_duration(active_hours[h])}")
        lines.append("")

    # Keylog snippets
    if summary["keylog_snippets"]:
        lines.append("📝 ÚLTIMAS DIGITAÇÕES")
        for s in summary["keylog_snippets"]:
            preview = s["text"].replace("\n", " ")[:80]
            lines.append(f"  [{s['time']}] {s['app']}: {preview}")
        lines.append("")

    lines.append(f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} pelo Tarcker")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

def render_html(summary: dict) -> str:
    day = summary["day"]

    # --- category rows ---
    cat_rows = ""
    for c in summary["cat_totals"]:
        emoji = CATEGORY_EMOJI.get(c["category"], "📦")
        pct = c["total_s"] / max(summary["active_s"], 1) * 100
        cat_rows += f"""
        <tr>
          <td>{emoji} {c['category'].capitalize()}</td>
          <td><div class="bar-wrap"><div class="bar" style="width:{pct:.0f}%"></div></div></td>
          <td class="right">{_fmt_duration(c['total_s'])}</td>
          <td class="right">{pct:.0f}%</td>
        </tr>"""

    # --- app rows ---
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

    # --- hourly bars ---
    max_hourly = max(summary["hourly"].values()) if any(summary["hourly"].values()) else 1
    hourly_bars = ""
    for h in range(24):
        val = summary["hourly"][h]
        pct = val / max_hourly * 100
        hourly_bars += f"""
        <div class="hour-col">
          <div class="hour-bar-wrap">
            <div class="hour-bar" style="height:{pct:.0f}%" title="{h:02d}h — {_fmt_duration(val)}"></div>
          </div>
          <div class="hour-label">{h:02d}</div>
        </div>"""

    # --- domain rows ---
    domain_rows = ""
    for d in summary["top_domains"]:
        domain_rows += f"""
        <tr>
          <td>🌐 {d['domain']}</td>
          <td class="right">{d['count']}</td>
        </tr>"""

    # --- search queries ---
    search_items = "".join(
        f"<li>{q}</li>" for q in summary["search_queries"][:20]
    ) or "<li><em>nenhuma</em></li>"

    # --- typing apps ---
    typing_rows = ""
    for a in summary["top_typing_apps"]:
        typing_rows += f"""
        <tr><td>{a['app']}</td><td class="right">{a['chars']:,}</td></tr>"""

    # --- keylog snippets ---
    snippet_html = ""
    for s in summary["keylog_snippets"]:
        text_escaped = (
            s["text"]
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("\n", "<br>")
        )
        snippet_html += f"""
        <div class="snippet">
          <div class="snippet-meta">{s['time']} · {s['app']} · <em>{s['title']}</em></div>
          <div class="snippet-text">{text_escaped}</div>
        </div>"""

    # --- screenshot thumbnails ---
    ss_html = ""
    for ss in summary["screenshots"][:48]:  # max 48 thumbs
        p = Path(ss["filepath"])
        if p.exists():
            import base64
            try:
                thumb_b64 = base64.b64encode(p.read_bytes()).decode()
                ts = ss["timestamp"][11:16]
                ss_html += f"""
                <div class="thumb">
                  <img src="data:image/jpeg;base64,{thumb_b64}"
                       title="{ts} — {ss.get('app_name','')}" loading="lazy">
                  <div class="thumb-label">{ts}</div>
                </div>"""
            except Exception:
                pass

    first = summary["first_seen"].strftime("%H:%M") if summary["first_seen"] else "—"
    last  = summary["last_seen"].strftime("%H:%M") if summary["last_seen"] else "—"

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Tarcker — {day.strftime('%d/%m/%Y')}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0f1117; color: #e2e8f0; padding: 2rem; max-width: 1200px; margin: 0 auto; }}
    h1 {{ font-size: 1.8rem; margin-bottom: .25rem; color: #f8fafc; }}
    .subtitle {{ color: #94a3b8; margin-bottom: 2rem; font-size: .95rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
             gap: 1rem; margin-bottom: 2rem; }}
    .card {{ background: #1e2130; border-radius: 12px; padding: 1.25rem;
             border: 1px solid #2d3148; }}
    .card .label {{ font-size: .75rem; color: #94a3b8; margin-bottom: .35rem;
                    text-transform: uppercase; letter-spacing: .05em; }}
    .card .value {{ font-size: 1.5rem; font-weight: 700; color: #f8fafc; }}
    section {{ background: #1e2130; border-radius: 12px; padding: 1.5rem;
               border: 1px solid #2d3148; margin-bottom: 1.5rem; }}
    section h2 {{ font-size: .85rem; color: #94a3b8; margin-bottom: 1rem;
                  text-transform: uppercase; letter-spacing: .06em; }}
    .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }}
    table {{ width: 100%; border-collapse: collapse; }}
    td, th {{ padding: .45rem .75rem; text-align: left; font-size: .88rem; }}
    tr:not(:last-child) td {{ border-bottom: 1px solid #2d3148; }}
    .right {{ text-align: right; }}
    .rank {{ color: #64748b; width: 2rem; }}
    .bar-wrap {{ background: #2d3148; border-radius: 4px; height: 8px; min-width: 80px; }}
    .bar {{ background: linear-gradient(90deg, #6366f1, #a78bfa); height: 8px; border-radius: 4px; }}
    .hourly {{ display: flex; align-items: flex-end; gap: 2px; height: 120px; margin-top: .5rem; }}
    .hour-col {{ display: flex; flex-direction: column; align-items: center; flex: 1; }}
    .hour-bar-wrap {{ flex: 1; display: flex; align-items: flex-end; width: 100%; }}
    .hour-bar {{ background: linear-gradient(180deg, #6366f1, #818cf8);
                 width: 100%; border-radius: 3px 3px 0 0; min-height: 2px; }}
    .hour-label {{ font-size: .55rem; color: #475569; margin-top: 3px; }}
    .snippet {{ background: #161928; border-left: 3px solid #6366f1;
                border-radius: 4px; padding: .75rem 1rem; margin-bottom: .75rem; }}
    .snippet-meta {{ font-size: .75rem; color: #64748b; margin-bottom: .3rem; }}
    .snippet-text {{ font-family: 'Consolas', monospace; font-size: .82rem;
                     color: #cbd5e1; white-space: pre-wrap; word-break: break-word; }}
    .thumbs {{ display: flex; flex-wrap: wrap; gap: .5rem; margin-top: .5rem; }}
    .thumb {{ text-align: center; }}
    .thumb img {{ width: 180px; height: 112px; object-fit: cover;
                  border-radius: 6px; border: 1px solid #2d3148;
                  cursor: pointer; transition: opacity .2s; }}
    .thumb img:hover {{ opacity: .8; }}
    .thumb-label {{ font-size: .65rem; color: #64748b; margin-top: 2px; }}
    ul.searches {{ list-style: none; columns: 2; }}
    ul.searches li {{ padding: .2rem 0; font-size: .88rem; color: #cbd5e1; }}
    ul.searches li::before {{ content: "🔍 "; }}
    footer {{ text-align: center; color: #475569; font-size: .78rem; margin-top: 2rem; }}
    /* lightbox */
    #lb {{ display:none; position:fixed; inset:0; background:rgba(0,0,0,.85);
           z-index:999; align-items:center; justify-content:center; cursor:zoom-out; }}
    #lb.open {{ display:flex; }}
    #lb img {{ max-width:95vw; max-height:95vh; border-radius:8px; }}
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
    <div class="card"><div class="label">Início / Fim</div>
      <div class="value" style="font-size:1.1rem">{first} – {last}</div></div>
    <div class="card"><div class="label">Teclas Digitadas</div>
      <div class="value">{summary['total_chars']:,}</div></div>
    <div class="card"><div class="label">Sites Visitados</div>
      <div class="value">{summary['browser_visits']}</div></div>
    <div class="card"><div class="label">Screenshots</div>
      <div class="value">{summary['screenshot_count']}</div></div>
  </div>

  <section>
    <h2>⏰ Atividade por Hora</h2>
    <div class="hourly">{hourly_bars}</div>
  </section>

  <div class="two-col">
    <section>
      <h2>🗂️ Categorias</h2>
      <table>{cat_rows}</table>
    </section>
    <section>
      <h2>🏆 Top Aplicativos</h2>
      <table>
        <tr><th></th><th>App</th><th class="right">Tempo</th><th class="right">%</th></tr>
        {app_rows}
      </table>
    </section>
  </div>

  <div class="two-col">
    <section>
      <h2>🌐 Top Sites</h2>
      <table>
        <tr><th>Domínio</th><th class="right">Visitas</th></tr>
        {domain_rows}
      </table>
    </section>
    <section>
      <h2>⌨️ Digitação por App</h2>
      <table>
        <tr><th>App</th><th class="right">Chars</th></tr>
        {typing_rows}
      </table>
    </section>
  </div>

  <section>
    <h2>🔍 Buscas Realizadas</h2>
    <ul class="searches">{search_items}</ul>
  </section>

  <section>
    <h2>📝 Últimas Digitações</h2>
    {snippet_html or '<p style="color:#64748b">Nenhuma digitação registrada.</p>'}
  </section>

  {'<section><h2>🖼️ Screenshots do Dia</h2><div class="thumbs">' + ss_html + '</div></section>'
   if ss_html else ''}

  <div id="lb" onclick="this.classList.remove('open')">
    <img id="lb-img" src="">
  </div>
  <script>
    document.querySelectorAll('.thumb img').forEach(img => {{
      img.addEventListener('click', e => {{
        e.stopPropagation();
        document.getElementById('lb-img').src = img.src;
        document.getElementById('lb').classList.add('open');
      }});
    }});
  </script>

  <footer>Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} pelo Tarcker</footer>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Save HTML report
# ---------------------------------------------------------------------------

def save_html_report(summary: dict) -> Path:
    config = load_config()
    output_dir = Path(config["html_report"]["output_dir"]).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"tarcker_{summary['day'].isoformat()}.html"
    path.write_text(render_html(summary), encoding="utf-8")
    return path
