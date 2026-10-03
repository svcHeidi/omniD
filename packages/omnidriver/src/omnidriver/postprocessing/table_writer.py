"""Standard tabular output with a comment envelope: entry name, units and a UTC timestamp."""
from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TableWriter:
    """Write entry summary tables as CSV (with comment envelope) and HTML."""

    @staticmethod
    def write(
        rows: list[dict[str, Any]],
        output_dir: str | Path,
        filename_stem: str,
        label: str,
        entry: str,
        units: Mapping[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Write *rows* as ``<filename_stem>.csv`` and ``<filename_stem>.html``
        under ``output_dir``, each prefixed by an envelope naming *entry*, the
        column-name-to-unit mapping *units* and the UTC time of writing.
        ``rows`` may be empty (only the envelope is written). Returns two
        artifact dicts (csv, html) with keys ``path`` (a relative filename),
        ``label``, ``kind`` and ``format``.
        """
        units = dict(units or {})
        generated_at = datetime.now(timezone.utc).isoformat()
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        csv_path = output_dir / f"{filename_stem}.csv"
        html_path = output_dir / f"{filename_stem}.html"

        fieldnames: list[str] = list(rows[0].keys()) if rows else []

        lines: list[str] = [
            f"# entry: {entry}",
            f"# generated_at: {generated_at}",
            f"# units: {json.dumps(units)}",
        ]
        if fieldnames:
            lines.append(",".join(fieldnames))
            for row in rows:
                lines.append(",".join(str(row.get(f, "")) for f in fieldnames))
        csv_path.write_text("\n".join(lines) + "\n")

        parts: list[str] = [
            "<!DOCTYPE html><html><head>",
            "<style>",
            "body{font-family:Arial,sans-serif;margin:20px}",
            "table{border-collapse:collapse;width:100%}",
            "th,td{border:1px solid #ccc;padding:6px 10px;text-align:left}",
            "th{background:#f0f0f0}",
            ".meta{color:#555;margin-bottom:14px;font-size:13px;line-height:1.6}",
            "</style></head><body>",
            "<div class='meta'>",
            f"<strong>entry:</strong> {entry}&nbsp;&nbsp;",
            f"<strong>generated_at:</strong> {generated_at}<br>",
            f"<strong>units:</strong> {json.dumps(units)}",
            "</div>",
            "<table><thead><tr>",
        ]
        for f in fieldnames:
            parts.append(f"<th>{f}</th>")
        parts.append("</tr></thead><tbody>")
        for row in rows:
            parts.append("<tr>")
            for f in fieldnames:
                parts.append(f"<td>{row.get(f, '')}</td>")
            parts.append("</tr>")
        parts.append("</tbody></table></body></html>")
        html_path.write_text("".join(parts))

        return [
            {
                "path": csv_path.name,
                "label": label,
                "kind": "table",
                "format": "csv",
            },
            {
                "path": html_path.name,
                "label": label,
                "kind": "table",
                "format": "html",
            },
        ]
