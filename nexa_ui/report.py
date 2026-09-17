"""
NEXA UI - Session report generation

Produces a self-contained HTML report of a session: participant identifier,
session metadata, and the measured values returned by each modality program.

The report contains measurements and descriptive statistics only. It contains
no interpretation, no reference-range comparison, no severity scoring, and
no diagnostic or predictive statement of any kind.
"""

import html
import os
from datetime import datetime

import config
import modalities


CSS = """
body { font-family: -apple-system, "Segoe UI", "DejaVu Sans", sans-serif;
       margin: 0; padding: 32px; color: #1b2229; background: #ffffff; }
h1 { font-size: 24px; margin: 0 0 4px 0; }
h2 { font-size: 17px; margin: 28px 0 10px 0; border-bottom: 2px solid #e3e8ee;
     padding-bottom: 6px; }
.sub { color: #667380; font-size: 13px; margin: 0 0 20px 0; }
table { border-collapse: collapse; width: 100%; margin-bottom: 8px; font-size: 14px; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #e8ecf1; }
th { background: #f4f7fa; font-weight: 600; width: 34%; }
.metrics td { width: 25%; }
.metric-value { font-size: 19px; font-weight: 600; color: #1b2229; }
.metric-label { font-size: 11px; color: #667380; text-transform: uppercase;
                letter-spacing: 0.4px; }
.status-completed { color: #17794a; font-weight: 600; }
.status-aborted { color: #9a6a00; font-weight: 600; }
.status-failed { color: #b3261e; font-weight: 600; }
.notice { margin-top: 36px; padding: 14px 16px; background: #fbf7ec;
          border-left: 4px solid #d8a93a; font-size: 12px; color: #5c4a1e; }
.notes { font-size: 13px; color: #44505c; font-style: italic; }
.empty { color: #8a949e; font-size: 13px; }
"""


def _esc(v):
    return html.escape("" if v is None else str(v))


def build_session_html(db, session_id):
    session = db.get_session(session_id)
    if session is None:
        raise ValueError(f"Session {session_id} not found")
    participant = db.get_participant(session["participant_id"])
    runs = db.list_runs(session_id)

    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>NEXA Session {session_id}</title>",
        f"<style>{CSS}</style></head><body>",
        "<h1>NEXA Assessment Session Report</h1>",
        f"<p class='sub'>Generated {_esc(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}</p>",
    ]

    # Participant + session metadata
    parts.append("<h2>Session</h2><table>")
    parts.append(f"<tr><th>Participant code</th><td>{_esc(participant['code'])}</td></tr>")
    if participant["display_name"]:
        parts.append(f"<tr><th>Name / label</th><td>{_esc(participant['display_name'])}</td></tr>")
    if participant["birth_year"]:
        parts.append(f"<tr><th>Birth year</th><td>{_esc(participant['birth_year'])}</td></tr>")
    if participant["handedness"]:
        parts.append(f"<tr><th>Handedness</th><td>{_esc(participant['handedness'])}</td></tr>")
    parts.append(f"<tr><th>Session ID</th><td>{session_id}</td></tr>")
    parts.append(f"<tr><th>Operator</th><td>{_esc(session['operator'])}</td></tr>")
    parts.append(f"<tr><th>Started</th><td>{_esc(session['started_at'])}</td></tr>")
    parts.append(f"<tr><th>Ended</th><td>{_esc(session['ended_at'] or 'in progress')}</td></tr>")
    parts.append("</table>")

    if session["notes"]:
        parts.append(f"<p class='notes'>Session notes: {_esc(session['notes'])}</p>")

    # Per-modality results
    if not runs:
        parts.append("<h2>Measurements</h2><p class='empty'>No assessments recorded.</p>")
    else:
        for run in runs:
            modality = modalities.get(run["modality"])
            name = modality.name if modality else run["modality"]
            parts.append(f"<h2>{_esc(name)}</h2>")

            status = run["status"]
            parts.append(
                f"<p class='sub'>Recorded {_esc(run['started_at'])} — "
                f"<span class='status-{_esc(status)}'>{_esc(status)}</span></p>"
            )

            metrics = db.run_metrics(run)
            if modality:
                formatted = modality.format_metrics(metrics)
            else:
                formatted = [(k, "—" if v is None else f"{v}") for k, v in metrics.items()]

            if formatted:
                parts.append("<table class='metrics'><tr>")
                for label, value in formatted:
                    parts.append(
                        f"<td><div class='metric-value'>{_esc(value)}</div>"
                        f"<div class='metric-label'>{_esc(label)}</div></td>"
                    )
                parts.append("</tr></table>")
            else:
                parts.append("<p class='empty'>No metrics recorded.</p>")

            if run["operator_notes"]:
                parts.append(f"<p class='notes'>Operator notes: {_esc(run['operator_notes'])}</p>")
            if run["raw_path"]:
                parts.append(f"<p class='sub'>Raw data: {_esc(run['raw_path'])}</p>")

    parts.append(f"<div class='notice'>{_esc(config.RESEARCH_NOTICE)}</div>")
    parts.append("</body></html>")
    return "".join(parts)


def write_session_report(db, session_id, directory=None):
    """Write the HTML report to disk and return its path."""
    config.ensure_dirs()
    directory = directory or config.REPORT_DIR
    content = build_session_html(db, session_id)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(directory, f"nexa_session_{session_id:05d}_{stamp}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path