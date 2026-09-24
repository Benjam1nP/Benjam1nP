"""Build the streak and monthly-activity cards shown on the profile README.

Reads the public contribution calendar from github.com (no token needed) and
writes light and dark SVGs into assets/. Run by .github/workflows/cards.yml.
"""

import datetime as dt
import html
import json
import re
import urllib.request
from pathlib import Path

USER = "Benjam1nP"
ASSETS = Path(__file__).resolve().parent.parent / "assets"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"

THEMES = {
    "light": dict(bg="#FFFFFF", border="#D0D7DE", title="#121214", muted="#8C959F",
                  label="#57606A", tile="#F6F8FA", grid="#EAEEF2", bar="#121214"),
    "dark": dict(bg="#0D1117", border="#30363D", title="#F0F6FC", muted="#7D8590",
                 label="#9198A1", tile="#161B22", grid="#21262D", bar="#F0F6FC"),
}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": f"{USER}-profile-cards"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def account_created():
    data = json.loads(get(f"https://api.github.com/users/{USER}"))
    return dt.date.fromisoformat(data["created_at"][:10])


def contributions(start, today):
    """Return {date: count} from the account's first year up to today."""
    days = {}
    for year in range(start.year, today.year + 1):
        page = get(f"https://github.com/users/{USER}/contributions?from={year}-01-01&to={year}-12-31")
        cells = dict((cid, d) for d, cid in re.findall(r'data-date="([\d-]+)" id="([^"]+)"', page))
        for cid, text in re.findall(r'<tool-tip[^>]*for="([^"]+)"[^>]*>([^<]*)', page):
            if cid not in cells:
                continue
            m = re.match(r"\s*([\d,]+) contribution", text)
            day = dt.date.fromisoformat(cells[cid])
            if start <= day <= today:
                days[day] = int(m.group(1).replace(",", "")) if m else 0
    return days


def fmt_date(d):
    return f"{d:%b} {d.day}, {d.year}"


def streaks(days, today):
    ordered = sorted(days)
    longest = (0, None, None)
    run, run_start = 0, None
    for d in ordered:
        if days[d] > 0:
            run_start = d if run == 0 else run_start
            run += 1
            if run > longest[0]:
                longest = (run, run_start, d)
        else:
            run = 0
    # A day without contributions yet today does not break the current streak.
    cursor = today if days.get(today, 0) > 0 else today - dt.timedelta(days=1)
    current_end, current = cursor, 0
    while days.get(cursor, 0) > 0:
        current += 1
        cursor -= dt.timedelta(days=1)
    current_start = cursor + dt.timedelta(days=1)
    return (current, current_start, current_end), longest


def svg_open(width, height, label, t):
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="{FONT}" role="img" aria-label="{html.escape(label)}">',
        f'  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="8" fill="{t["bg"]}" stroke="{t["border"]}"/>',
    ]


def streak_svg(t, total, since, current, longest):
    def span(s):
        n, a, b = s
        return f"{fmt_date(a)} to {fmt_date(b)}" if n else "No active streak"

    cols = [
        (f"{total:,}", "Total contributions", f"{fmt_date(since)} to present"),
        (f"{current[0]}", "Current streak", span(current)),
        (f"{longest[0]}", "Longest streak", span(longest)),
    ]
    label = f"{total} total contributions, {current[0]} day current streak, {longest[0]} day longest streak"
    out = svg_open(860, 190, label, t)
    out.append(f'  <text x="24" y="34" font-size="16" font-weight="600" fill="{t["title"]}">Consistency</text>')
    out.append(f'  <text x="24" y="52" font-size="12" fill="{t["muted"]}">Contributions since {since.year}</text>')
    col_w = 812 / 3
    out.append(f'  <rect x="{24 + col_w:.1f}" y="64" width="{col_w:.1f}" height="108" rx="8" fill="{t["tile"]}"/>')
    for i, (value, name, sub) in enumerate(cols):
        x = 24 + col_w * i + col_w / 2
        out.append(f'  <text x="{x:.1f}" y="108" text-anchor="middle" font-size="40" font-weight="700" fill="{t["title"]}">{value}</text>')
        out.append(f'  <text x="{x:.1f}" y="134" text-anchor="middle" font-size="13" font-weight="600" fill="{t["label"]}">{name}</text>')
        out.append(f'  <text x="{x:.1f}" y="154" text-anchor="middle" font-size="11" fill="{t["muted"]}">{sub}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def last_twelve_months(days, today):
    months = []
    y, m = today.year, today.month
    for _ in range(12):
        months.append((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    months.reverse()
    totals = {ym: 0 for ym in months}
    for d, n in days.items():
        if (d.year, d.month) in totals:
            totals[(d.year, d.month)] += n
    return [(y, m, totals[(y, m)]) for y, m in months]


def nice_step(peak):
    """Grid step so that two steps cover the tallest bar."""
    raw = max(peak, 1) / 2
    magnitude = 10 ** (len(str(int(raw))) - 1)
    for mult in (1, 2, 2.5, 5, 10):
        if magnitude * mult >= raw:
            return int(magnitude * mult) or 1
    return int(raw)


def activity_svg(t, months):
    first, last = months[0], months[-1]
    period = f"{dt.date(first[0], first[1], 1):%b %Y} to {dt.date(last[0], last[1], 1):%b %Y}"
    total = sum(n for _, _, n in months)
    step = nice_step(max(n for _, _, n in months))
    base, top = 208.0, 68.0
    scale = (base - top) / (step * 2)

    out = svg_open(860, 260, f"Contributions by month, {period}", t)
    out.append(f'  <text x="24" y="34" font-size="16" font-weight="600" fill="{t["title"]}">Contributions by month</text>')
    out.append(f'  <text x="24" y="52" font-size="12" fill="{t["muted"]}">{period}</text>')
    out.append(f'  <text x="836" y="34" text-anchor="end" font-size="16" font-weight="600" fill="{t["title"]}">{total:,}</text>')
    out.append(f'  <text x="836" y="52" text-anchor="end" font-size="12" fill="{t["muted"]}">total</text>')
    out.append("  <g>")
    for i in range(3):
        y = base - i * step * scale
        out.append(f'    <line x1="52" y1="{y:.1f}" x2="836" y2="{y:.1f}" stroke="{t["grid"]}" stroke-width="1"/>')
        out.append(f'    <text x="40" y="{y + 4:.1f}" text-anchor="end" font-size="11" fill="{t["muted"]}">{i * step}</text>')
    out.append("  </g>")
    out.append("  <g>")
    slot = (836 - 52) / 12
    for i, (y, m, n) in enumerate(months):
        cx = 52 + slot * i + slot / 2
        h = max(n * scale, 3.0)
        radius = min(3.0, h / 2)
        out.append(f'    <rect x="{cx - 17:.1f}" y="{base - h:.1f}" width="34.0" height="{h:.1f}" rx="{radius:.1f}" fill="{t["bar"]}"/>')
        out.append(f'    <text x="{cx:.1f}" y="{base - h - 8:.1f}" text-anchor="middle" font-size="11" font-weight="600" fill="{t["label"]}">{n}</text>')
        out.append(f'    <text x="{cx:.1f}" y="228" text-anchor="middle" font-size="12" fill="{t["label"]}">{dt.date(y, m, 1):%b}</text>')
        if i == 0 or m == 1:
            out.append(f'    <text x="{cx:.1f}" y="244" text-anchor="middle" font-size="10" fill="{t["muted"]}">{y}</text>')
    out.append("  </g>")
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main():
    today = dt.datetime.now(dt.timezone.utc).date()
    since = account_created()
    days = contributions(since, today)
    total = sum(days.values())
    current, longest = streaks(days, today)
    months = last_twelve_months(days, today)

    ASSETS.mkdir(exist_ok=True)
    for name, t in THEMES.items():
        (ASSETS / f"streak-{name}.svg").write_text(streak_svg(t, total, since, current, longest), encoding="utf-8")
        (ASSETS / f"activity-{name}.svg").write_text(activity_svg(t, months), encoding="utf-8")
    print(f"{total} contributions, current streak {current[0]}, longest {longest[0]}")


if __name__ == "__main__":
    main()
