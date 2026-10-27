#!/usr/bin/env python3
"""Check foundation documents and attribution in explicitly selected new commits."""

import argparse
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "LICENSE",
    "docs/PRODUCT.md",
    "docs/THESIS.md",
    "docs/STATUS.md",
    "docs/ARCHITECTURE.md",
    "docs/PROTOCOL.md",
    "docs/EXTENSIONS.md",
    "docs/CODING_STYLE.md",
    "docs/TESTING.md",
    "docs/PERFORMANCE.md",
    "docs/RESEARCH.md",
    "docs/decisions/0001-stack.md",
)
ATTRIBUTION = re.compile(
    r"^\s*co[- ]authored[- ]by\s*:"
    r"|(?:generated|authored|written|committed|assisted|powered)\s+"
    r"(?:with|by|using)\s+[^\n]*\b(?:claude|codex|copilot|chatgpt|cursor|aider|gemini|ai|agent)\b"
    r"|^\s*(?:ai|agent)[- ](?:assisted|generated)\s*(?:commit|change|code)"
    r"|^\s*(?:author|coauthor|co-author|credits?|thanks(?: to)?)\s*:\s*"
    r"[^\n]*\b(?:claude|codex|copilot|chatgpt|cursor|aider|gemini|agent)\b",
    re.IGNORECASE | re.MULTILINE,
)
AGENT_IDENTITY = re.compile(
    r"\b(?:claude|codex|copilot|chatgpt|aider)\b|cursor\s+agent"
    r"|(?:noreply|no-reply)@(?:anthropic|openai)\.com",
    re.IGNORECASE,
)
LINK = re.compile(r"\[[^\]]*\]\(([^\s)]+)(?:\s+[^)]*)?\)")
HTML_LINK = re.compile(r"\b(?:href|src)=[\"']([^\"']+)[\"']", re.IGNORECASE)
LOCAL_ONLY_PREFIXES = (".local/", "tmp/")
LOCAL_ONLY_FILES = {"docs/BUILD_PLAN.md", "docs/STRATEGY_REVIEW_2026-10-28.md"}


def local_path_errors(paths: list[str]) -> list[str]:
    return [
        f"local-only file must not be tracked: {path}"
        for path in paths
        if path.startswith(LOCAL_ONLY_PREFIXES) or path in LOCAL_ONLY_FILES
    ]


def message_errors(message: str, identity: str = "") -> list[str]:
    errors = []
    if ATTRIBUTION.search(message):
        errors.append("commit message contains a coauthor trailer or coding-agent attribution")
    if identity and AGENT_IDENTITY.search(identity):
        errors.append("commit author or committer is a recognizable coding-agent identity")
    return errors


def document_errors(root: Path) -> list[str]:
    errors = [f"missing required file: {name}" for name in REQUIRED if not (root / name).is_file()]
    documents = list(root.glob("*.md")) + list((root / "docs").rglob("*.md"))
    documents += list((root / ".github").rglob("*.md"))
    for document in documents:
        body = document.read_text(encoding="utf-8")
        if not body.strip():
            errors.append(f"empty document: {document.relative_to(root)}")
        for target in LINK.findall(body) + HTML_LINK.findall(body):
            parsed = urlsplit(target.strip("<>"))
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            resolved = (document.parent / unquote(parsed.path)).resolve()
            if not resolved.is_relative_to(root.resolve()) or not resolved.exists():
                errors.append(f"broken local link: {document.relative_to(root)} -> {target}")
    claude = root / "CLAUDE.md"
    if claude.is_file() and "[AGENTS.md](AGENTS.md)" not in claude.read_text():
        errors.append("CLAUDE.md must link to the shared AGENTS.md instructions")
    agents = root / "AGENTS.md"
    if agents.is_file() and "docs/CODING_STYLE.md" not in agents.read_text():
        errors.append("AGENTS.md must direct contributors to the coding standards")
    return errors


def git(*arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True)


def commit_errors(revision_range: str) -> list[str]:
    if ".." not in revision_range or revision_range.startswith("-"):
        raise ValueError("select only new commits with an explicit BASE..HEAD range")
    errors = []
    for commit in git("rev-list", revision_range, "--").splitlines():
        message = git("show", "-s", "--format=%B", commit)
        identity = git("show", "-s", "--format=%an <%ae>%n%cn <%ce>", commit)
        errors.extend(f"{commit[:12]}: {error}" for error in message_errors(message, identity))
    return errors


def event_range(event_path: Path) -> str | None:
    event = json.loads(event_path.read_text())
    if "pull_request" in event:
        request = event["pull_request"]
        return f"{request['base']['sha']}..{request['head']['sha']}"
    before, after = event.get("before"), event.get("after")
    # A new ref has no integration base; do not accidentally audit all old history.
    if before and after and set(before) != {"0"} and set(after) != {"0"}:
        return f"{before}..{after}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commits", help="explicit new-commit range, such as origin/main..HEAD")
    parser.add_argument("--message-file", type=Path, help="check a proposed commit message")
    parser.add_argument("--event-path", type=Path, help="derive the new-commit range from a CI event")
    args = parser.parse_args()
    try:
        errors = [] if args.message_file else document_errors(ROOT)
        if not args.message_file:
            # Check the index so force-adding an ignored plan still blocks publication.
            errors.extend(local_path_errors(git("ls-files", "-z").strip("\0").split("\0")))
        if args.message_file:
            errors.extend(message_errors(args.message_file.read_text(encoding="utf-8")))
        revision_range = args.commits or (event_range(args.event_path) if args.event_path else None)
        if revision_range:
            errors.extend(commit_errors(revision_range))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Repository check could not complete: {error}")
        return 1
    if errors:
        for error in errors:
            print(error)
        return 1
    print("Repository checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
