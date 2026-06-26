#!/usr/bin/env python3
"""Tests for continuum-attach-grace's should_reset() decision.

stdlib-only; run with:  uv run python bin/test_continuum_attach_grace.py
Exits non-zero on any failure.
"""
import importlib.util
import os
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))


def _load():
    loader = SourceFileLoader("continuum_attach_grace",
                              os.path.join(HERE, "continuum-attach-grace"))
    spec = importlib.util.spec_from_loader("continuum_attach_grace", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


cag = _load()
INTERVAL = 900  # 15 min in seconds


def case(name, fn):
    try:
        fn()
    except AssertionError as e:
        print(f"FAIL {name}: {e}")
        return False
    print(f"ok   {name}")
    return True


def test_reset_when_unset():
    # No prior save timestamp (fresh option) -> attaching could fire an
    # immediate save; reset to grant a grace window.
    assert cag.should_reset(1000, "", INTERVAL) is True


def test_reset_when_zero():
    # continuum's default when the option is read but unset is "0" (epoch 1970).
    assert cag.should_reset(1000000, "0", INTERVAL) is True


def test_reset_when_stale():
    # last save 950s ago, interval 900s -> the gate would already pass -> reset.
    assert cag.should_reset(1000, "50", INTERVAL) is True


def test_no_reset_when_fresh():
    # last save 500s ago (< interval) -> no immediate save would fire -> leave it.
    assert cag.should_reset(1000, "500", INTERVAL) is False


def test_reset_when_garbage():
    # Unparseable stored value -> reset rather than risk an immediate save.
    assert cag.should_reset(1000, "not-a-number", INTERVAL) is True


def main():
    cases = [
        ("reset_when_unset", test_reset_when_unset),
        ("reset_when_zero", test_reset_when_zero),
        ("reset_when_stale", test_reset_when_stale),
        ("no_reset_when_fresh", test_no_reset_when_fresh),
        ("reset_when_garbage", test_reset_when_garbage),
    ]
    ok = all(case(n, f) for n, f in cases)
    print("PASS" if ok else "FAILED")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
