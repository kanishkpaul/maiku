"""Exercise attribution rejection and CI integration-base selection."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_repository import event_range, message_errors


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
