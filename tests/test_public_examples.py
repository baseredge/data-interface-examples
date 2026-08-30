from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIRS = (ROOT / "admin", ROOT / "http", ROOT / "websocket")


class PublicExamplesTest(unittest.TestCase):
    def test_python_files_parse(self) -> None:
        files = [path for directory in PYTHON_DIRS for path in directory.glob("*.py")]
        self.assertTrue(files)
        for path in files:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


    def test_default_urls_are_local(self) -> None:
        for directory in PYTHON_DIRS:
            for path in directory.glob("*.py"):
                text = path.read_text(encoding="utf-8")
                urls = re.findall(r"(?:https?|wss?)://([^\s\"'`]+)", text)
                for authority in urls:
                    host = authority.split("/", 1)[0].rsplit(":", 1)[0]
                    self.assertTrue(host == "localhost" or host.startswith("127."), path)


if __name__ == "__main__":
    unittest.main()
