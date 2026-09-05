from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))

import render  # noqa: E402


class RuntimeBlockTests(unittest.TestCase):
    def test_uv_native_without_gpu_does_not_mention_mps(self) -> None:
        text = render.runtime_block(
            {"RUNTIME_MODE": "uv-native", "USE_GPU": "no", "LANGUAGE": "Python"}
        )
        self.assertNotIn("GPU/MPS", text)
        self.assertNotIn("MPS", text)

    def test_uv_native_with_gpu_mentions_mps(self) -> None:
        text = render.runtime_block(
            {"RUNTIME_MODE": "uv-native", "USE_GPU": "yes", "LANGUAGE": "Python"}
        )
        self.assertIn("GPU/MPS", text)
        self.assertIn("MPS", text)


if __name__ == "__main__":
    unittest.main()
