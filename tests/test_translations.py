"""Every UI string must have a finished Swedish translation (no Qt needed)."""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from compile_translations import MAGIC, compile_ts, read_ts  # noqa: E402

PLUGIN = ROOT / "ekonomiska_kartan"
TS = PLUGIN / "i18n" / "ekonomiska_kartan_sv.ts"
PLACEHOLDER = re.compile(r"\{\w+\}")


def strings_in_code():
    """{(context, text)} for self.tr("...") in the dock widget and translate("ctx", "...")."""
    found = set()
    for path in PLUGIN.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            for node in ast.walk(cls):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "tr"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    found.add((cls.name, node.args[0].value))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "translate"
                and len(node.args) >= 2
                and all(isinstance(a, ast.Constant) for a in node.args[:2])
            ):
                found.add((node.args[0].value, node.args[1].value))
    return found


def test_every_ui_string_is_translated():
    translated = {(c, s) for c, s, _comment, _t in read_ts(TS)}
    missing = sorted(strings_in_code() - translated)
    assert not missing, f"Add to {TS.name} (pylupdate, then translate): {missing}"


def test_placeholders_match():
    for _context, source, _comment, text in read_ts(TS):
        assert sorted(PLACEHOLDER.findall(source)) == sorted(PLACEHOLDER.findall(text)), source


def test_qm_is_built():
    data = compile_ts(TS)
    assert data.startswith(MAGIC) and len(data) > len(MAGIC) + 100
