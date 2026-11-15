from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "complexity.py"


def _complexity_module():
    spec = importlib.util.spec_from_file_location("trove_complexity", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_scan_files_include_kotlin_and_skip_tests_and_build_outputs():
    module = _complexity_module()
    assert module.is_scan_file("android/app/src/main/kotlin/dev/trove/app/MainActivity.kt")
    assert module.is_scan_file("src/trove/app.py")
    assert not module.is_scan_file("android/app/src/test/kotlin/dev/trove/app/AppSmokeTest.kt")
    assert not module.is_scan_file("android/app/build/generated/Foo.kt")
    assert not module.is_scan_file("android/gradlew.bat")


def test_parse_lizard_reads_cyclomatic_complexity_and_function_names():
    module = _complexity_module()
    report = (
        "9,3,63,0,9,\"restore@69-77@a.kt\",\"a.kt\",\"restore\",\"restore\",69,77\n"
        "37,10,285,3,39,\"login@79-117@b.kt\",\"b.kt\",\"login\",\"login body\",79,117\n"
    )
    metrics = module.parse_lizard(
        report,
        {
            str(Path("a.kt").resolve()): "src/main/a.kt",
            str(Path("b.kt").resolve()): "src/main/b.kt",
        },
    )
    assert metrics == {
        ("src/main/a.kt", "restore"): 3,
        ("src/main/b.kt", "login"): 10,
    }


def test_parse_lizard_ignores_malformed_rows():
    module = _complexity_module()
    assert module.parse_lizard("not,a,report\n1,2,3\n", {}) == {}


def test_sanitize_kotlin_rewrites_fun_interface_for_lizard():
    module = _complexity_module()
    source = "fun interface Listener {\n    fun onEvent(value: String)\n}\n"
    sanitized = module._sanitize_kotlin(source)
    assert "fun interface" not in sanitized
    assert "interface Listener" in sanitized
    assert sanitized.count("\n") == source.count("\n")
