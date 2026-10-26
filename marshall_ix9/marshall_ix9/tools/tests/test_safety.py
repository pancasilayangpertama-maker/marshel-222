"""Safety rules. These tests fail the GitHub build if anyone adds network code or obfuscation.

They only read the source files (nothing is imported or run), so they work on any computer.
"""
from __future__ import annotations

import ast
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class SafetyTests(unittest.TestCase):
    """The promises made in the README are enforced here, so a future edit cannot break them silently."""

    BANNED_IMPORTS = {
        "socket", "ssl", "http", "urllib", "ftplib", "smtplib", "poplib", "imaplib", "telnetlib",
        "xmlrpc", "requests", "webbrowser", "asyncio", "base64", "pickle", "marshal", "zlib",
    }
    BANNED_CALLS = {"eval", "exec", "compile", "__import__"}

    def _sources(self):
        for folder, _dirs, files in os.walk(os.path.join(ROOT, "marshall_ix9")):
            for name in files:
                if name.endswith(".py"):
                    yield os.path.join(folder, name)
        yield os.path.join(ROOT, "main.py")

    def test_no_network_modules_and_no_obfuscation_primitives(self):
        checked = 0
        for path in self._sources():
            with open(path, "r", encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), path)
            checked += 1
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots = {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    roots = {node.module.split(".")[0]}
                else:
                    roots = set()
                self.assertFalse(roots & self.BANNED_IMPORTS, f"{path}: forbidden import {roots & self.BANNED_IMPORTS}")
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, self.BANNED_CALLS, f"{path}: forbidden call {node.func.id}()")
        self.assertGreater(checked, 8)

    def test_only_expected_external_programs_are_launched(self):
        allowed = {"powercfg", "ipconfig", "powershell.exe"}
        found = set()
        for path in self._sources():
            with open(path, "r", encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "run" and node.args:
                    first = node.args[0]
                    if isinstance(first, ast.List) and first.elts and isinstance(first.elts[0], ast.Constant):
                        found.add(first.elts[0].value)
        self.assertTrue(found <= allowed, f"unexpected programs: {found - allowed}")
        self.assertTrue({"powercfg", "ipconfig", "powershell.exe"} <= found)


if __name__ == "__main__":
    unittest.main()
