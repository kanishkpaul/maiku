# ruff: noqa: E501
"""A local MCP casebook for the browser-controlled constellation demonstration.

It is intentionally a real stdio MCP server: its read, chart, and report-writing tools are
adapted by maiku exactly as a third-party MCP server would be. The report is written only
after the runtime has routed an approval request to the human in the browser.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path


def tools() -> list[dict]:
    return [
        {
            "name": "read_case_notes",
            "title": "Read the case notes",
            "description": "Read the local incident briefing supplied for this demonstration.",
            "inputSchema": {"type": "object", "properties": {}},
            "annotations": {"readOnlyHint": True, "idempotentHint": True},
        },
        {
            "name": "render_evidence_chart",
            "title": "Render evidence chart",
            "description": "Create an SVG evidence chart from the measured result.",
            "inputSchema": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "confidence": {"type": "number"}},
                "required": ["title", "confidence"],
            },
            "annotations": {"readOnlyHint": True},
        },
        {
            "name": "write_report",
            "title": "Write the incident report",
            "description": "Write the reviewed evidence report into the local casebook.",
            "inputSchema": {
                "type": "object",
                "properties": {"content": {"type": "string"}},
                "required": ["content"],
            },
        },
    ]


def chart(title: str, confidence: float) -> str:
    value = max(0, min(100, round(confidence * 100)))
    return f"""<svg xmlns='http://www.w3.org/2000/svg' width='720' height='220' viewBox='0 0 720 220'>
<rect width='720' height='220' fill='#0b1f1b'/><text x='34' y='52' fill='#dce7d1' font-family='Arial' font-size='22'>{title}</text>
<rect x='34' y='105' width='652' height='28' fill='#254a3e'/><rect x='34' y='105' width='{652 * value / 100:.0f}' height='28' fill='#c8ff54'/>
<text x='34' y='176' fill='#dce7d1' font-family='Arial' font-size='18'>measured confidence: {value}%</text></svg>"""


def dispatch(message: dict, case_dir: Path) -> dict:
    method = message.get("method")
    if method == "initialize":
        return {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "casebook", "title": "Casebook MCP", "version": "0.1.0"},
        }
    if method == "tools/list":
        return {"tools": tools()}
    if method != "tools/call":
        raise LookupError(method)

    params = message.get("params") or {}
    name, arguments = params.get("name"), params.get("arguments") or {}
    if name == "read_case_notes":
        text = (case_dir / "case-notes.md").read_text()
        return {"content": [{"type": "text", "text": text}]}
    if name == "render_evidence_chart":
        raw = chart(str(arguments["title"]), float(arguments["confidence"])).encode()
        return {
            "content": [
                {"type": "text", "text": "Evidence chart rendered as an SVG artifact."},
                {"type": "image", "data": base64.b64encode(raw).decode(), "mimeType": "image/svg+xml"},
            ]
        }
    if name == "write_report":
        reports = case_dir / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        path = reports / "evidence-report.md"
        path.write_text(str(arguments["content"]))
        return {"content": [{"type": "text", "text": f"Report written to {path}"}]}
    raise LookupError(name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", type=Path, required=True)
    args = parser.parse_args()
    args.case_dir.mkdir(parents=True, exist_ok=True)

    for raw in sys.stdin:
        if not raw.strip():
            continue
        message = json.loads(raw)
        if "id" not in message:
            continue
        try:
            result = dispatch(message, args.case_dir)
            response = {"jsonrpc": "2.0", "id": message["id"], "result": result}
        except LookupError as exc:
            response = {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": str(exc)}}
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
