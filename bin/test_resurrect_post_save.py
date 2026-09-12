#!/usr/bin/env python3
"""Tests for resurrect-post-save's pure logic (count_layout_text, is_degenerate).

stdlib-only; run with:  uv run python bin/test_resurrect_post_save.py
The file/subprocess orchestration (veto + logging) is covered by a separate
isolated integration test, not here.
"""
import importlib.util
import os
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))


def _load():
    loader = SourceFileLoader("resurrect_post_save",
                              os.path.join(HERE, "resurrect-post-save"))
    spec = importlib.util.spec_from_loader("resurrect_post_save", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


rps = _load()

# A realistic 2-pane / 2-window save (one grouped_session + one state line that
# must NOT be counted as panes or windows).
SAMPLE = "\n".join([
    "grouped_session\tdefault-1\tdefault\t:2\t:1",
    "pane\tdefault\t0\t1\t:*\t0\ttitle\t:/home/tim\t1\ttail\t:",
    "pane\tdefault\t1\t0\t:##\t0\ttitle\t:/home/tim\t1\tbash\t:",
    "window\tdefault\t0\t:h\t1\t:*\tlayout\toff",
    "window\tdefault\t1\t:bash\t0\t:##\tlayout\t:",
    "state\tdefault-1\t",
]) + "\n"


def case(name, fn):
    try:
        fn()
    except AssertionError as e:
        print(f"FAIL {name}: {e}")
        return False
    print(f"ok   {name}")
    return True


def test_count_layout_text():
    assert rps.count_layout_text(SAMPLE) == (2, 2), rps.count_layout_text(SAMPLE)


def test_count_layout_text_empty():
    assert rps.count_layout_text("") == (0, 0)


def test_count_layout_ignores_substring_types():
    # A pane_title containing the word "window" must not inflate the window count.
    text = "pane\tx\t0\t1\t:*\t0\twindow in title\t:/h\t1\tbash\t:\n"
    assert rps.count_layout_text(text) == (1, 0)


def test_is_degenerate_blocks_collapse():
    # 15-pane last -> 2-pane new: lost ~87% -> block.
    assert rps.is_degenerate(2, 15) is True


def test_is_degenerate_allows_modest_shrink():
    # 15 -> 8 is still substantial -> allow.
    assert rps.is_degenerate(8, 15) is False


def test_is_degenerate_allows_when_last_small():
    # last below the "rich enough to protect" floor -> never block.
    assert rps.is_degenerate(1, 4) is False


def test_is_degenerate_allows_growth():
    assert rps.is_degenerate(15, 2) is False


def test_is_degenerate_no_last():
    # First save / missing last -> nothing to protect.
    assert rps.is_degenerate(2, 0) is False


def main():
    cases = [
        ("count_layout_text", test_count_layout_text),
        ("count_layout_text_empty", test_count_layout_text_empty),
        ("count_layout_ignores_substring_types", test_count_layout_ignores_substring_types),
        ("is_degenerate_blocks_collapse", test_is_degenerate_blocks_collapse),
        ("is_degenerate_allows_modest_shrink", test_is_degenerate_allows_modest_shrink),
        ("is_degenerate_allows_when_last_small", test_is_degenerate_allows_when_last_small),
        ("is_degenerate_allows_growth", test_is_degenerate_allows_growth),
        ("is_degenerate_no_last", test_is_degenerate_no_last),
    ]
    ok = all(case(n, f) for n, f in cases)
    print("PASS" if ok else "FAILED")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
