from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "scripts" / "new-project.py"


def load_new_project():
    spec = importlib.util.spec_from_file_location("new_project", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class NewProjectTests(unittest.TestCase):
    def test_ignore_skips_git_github_and_reviews(self) -> None:
        new_project = load_new_project()
        skipped = new_project.ignore("/tmp/src", [".git", ".github", "README.md"])
        self.assertIn(".git", skipped)
        self.assertIn(".github", skipped)
        self.assertNotIn("README.md", skipped)
        grok = new_project.ignore("/tmp/src/.grok", ["reviews", "uc-plans", "skills"])
        self.assertIn("reviews", grok)
        self.assertIn("uc-plans", grok)
        self.assertNotIn("skills", grok)


if __name__ == "__main__":
    unittest.main()
