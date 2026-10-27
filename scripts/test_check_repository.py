"""Exercise attribution rejection and CI integration-base selection."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_repository import (
    REQUIRED,
    document_errors,
    event_range,
    local_path_errors,
    message_errors,
)


class PublicationChecks(unittest.TestCase):
    def test_rejects_tracked_planning_and_scratch_files(self):
        paths = [
            ".local/BUILD_PLAN.md",
            "tmp/session.txt",
            "docs/BUILD_PLAN.md",
            "docs/STRATEGY_REVIEW_2026-10-28.md",
        ]
        self.assertEqual(len(local_path_errors(paths)), len(paths))
        self.assertFalse(local_path_errors([
            "docs/THESIS.md", "docs/STATUS.md", "scripts/check_repository.py",
        ]))

    def make_foundation(self, root):
        for name in REQUIRED:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Foundation document.\n", encoding="utf-8")
        (root / "CLAUDE.md").write_text("Read [AGENTS.md](AGENTS.md).\n", encoding="utf-8")
        (root / "AGENTS.md").write_text("Read docs/CODING_STYLE.md.\n", encoding="utf-8")

    def test_public_foundation_does_not_require_private_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_foundation(root)
            self.assertFalse(document_errors(root))

    def test_checks_html_navigation_and_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_foundation(root)
            (root / "README.md").write_text(
                '<a href="docs/THESIS.md">Thesis</a>\n'
                '<img src="missing.svg" alt="Missing" />\n', encoding="utf-8")
            errors = document_errors(root)
            self.assertEqual(errors, ["broken local link: README.md -> missing.svg"])

    def test_rejects_links_outside_checkout_and_in_nested_templates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_foundation(root)
            template = root / ".github/ISSUE_TEMPLATE/bug.md"
            template.parent.mkdir(parents=True)
            template.write_text("[Outside](../../../outside.md)\n", encoding="utf-8")
            errors = document_errors(root)
            self.assertEqual(len(errors), 1)
            self.assertIn("broken local link", errors[0])


class AttributionChecks(unittest.TestCase):
    def test_rejects_coauthor_trailers_and_agent_signatures(self):
        messages = (
            "docs: revise plan\n\nCo-Authored-By: Claude <noreply@anthropic.com>",
            "fix: shutdown\n\nco authored by: another assistant",
            "runtime: cancel work\n\nGenerated with Claude Code",
            "docs: revise plan\n\nWritten by Codex",
            "runtime: cancel work\n\nCredits: Copilot",
        )
        for message in messages:
            with self.subTest(message=message):
                self.assertTrue(message_errors(message))

    def test_allows_ordinary_changes_to_agent_instruction_files(self):
        self.assertFalse(message_errors("docs: add CLAUDE.md and shared agent instructions"))
        self.assertFalse(message_errors("runtime: add a remote agent participant"))

    def test_checks_author_and_committer(self):
        self.assertTrue(message_errors("runtime: add tasks", "Codex <bot@example.com>"))
        self.assertFalse(message_errors("runtime: add tasks", "Maintainer <person@example.com>"))


class EventRanges(unittest.TestCase):
    def resolve(self, event):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "event.json"
            path.write_text(json.dumps(event))
            return event_range(path)

    def test_push_checks_only_new_commits(self):
        self.assertEqual(self.resolve({"before": "a" * 40, "after": "b" * 40}),
                         f"{'a' * 40}..{'b' * 40}")

    def test_pull_request_uses_its_actual_base_and_head(self):
        event = {"pull_request": {"base": {"sha": "base"}, "head": {"sha": "head"}}}
        self.assertEqual(self.resolve(event), "base..head")

    def test_new_ref_does_not_scan_historical_commits(self):
        self.assertIsNone(self.resolve({"before": "0" * 40, "after": "b" * 40}))


if __name__ == "__main__":
    unittest.main()
