#!/usr/bin/env python3
"""Tests for claude-resume's confirmation messaging (announce_decision).

Self-contained / stdlib-only to match the script it tests — run with:
    uv run python bin/test_claude_resume.py
Exits non-zero if any case fails; prints one line per case.

announce_decision() is the unit under test because the script's resume path
ends in os.execvp() (replaces the process); the decision + the line it prints
are factored out so they can be checked without a real stdin or exec.
"""
import importlib.util
import io
import os
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))


def _load():
    """Import the hyphenated, extension-less `claude-resume` as a module.

    spec_from_file_location() can't infer a loader without a `.py` suffix, so
    hand it an explicit SourceFileLoader."""
    loader = SourceFileLoader("claude_resume", os.path.join(HERE, "claude-resume"))
    spec = importlib.util.spec_from_loader("claude_resume", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


cr = _load()
SID = "37342e03-e5ff-4e89-9751-39ac24cfd9df"

# tty=False everywhere so output carries no ANSI escapes — substring asserts stay
# readable. (tty only toggles colour; it doesn't change the words or the result.)


def enter():
    """input()-like: a bare Enter returns the empty line."""
    return ""


def ctrl_c():
    raise KeyboardInterrupt


def ctrl_d():
    raise EOFError


def must_not_read():
    raise AssertionError("read_line() called when stdin is not a tty")


def case(name, fn):
    try:
        fn()
    except AssertionError as e:
        print(f"FAIL {name}: {e}")
        return False
    print(f"ok   {name}")
    return True


def test_enter_resumes_and_announces_session():
    out = io.StringIO()
    decision = cr.announce_decision(SID, False, True, enter, out)
    assert decision == "resume", f"expected 'resume', got {decision!r}"
    text = out.getvalue()
    assert "resuming" in text, f"no 'resuming' in {text!r}"
    assert SID[:8] in text, f"no session prefix {SID[:8]!r} in {text!r}"


def test_ctrl_c_skips_and_announces():
    out = io.StringIO()
    decision = cr.announce_decision(SID, False, True, ctrl_c, out)
    assert decision == "skip", f"expected 'skip', got {decision!r}"
    assert "skipped" in out.getvalue(), f"no 'skipped' in {out.getvalue()!r}"


def test_ctrl_d_skips_and_announces():
    out = io.StringIO()
    decision = cr.announce_decision(SID, False, True, ctrl_d, out)
    assert decision == "skip", f"expected 'skip', got {decision!r}"
    assert "skipped" in out.getvalue(), f"no 'skipped' in {out.getvalue()!r}"


def test_non_tty_resumes_without_reading():
    out = io.StringIO()
    # stdin not a tty (resurrect send-keys restore): no keypress to wait on.
    decision = cr.announce_decision(SID, False, False, must_not_read, out)
    assert decision == "resume", f"expected 'resume', got {decision!r}"
    assert "resuming" in out.getvalue(), f"no 'resuming' in {out.getvalue()!r}"


def test_no_sid_announces_picker():
    out = io.StringIO()
    decision = cr.announce_decision("", False, True, enter, out)
    assert decision == "resume", f"expected 'resume', got {decision!r}"
    assert "picker" in out.getvalue(), f"no 'picker' in {out.getvalue()!r}"


# --- main() wiring: prove the decision actually gates the exec --------------
FAKE_SID = "00000000-0000-0000-0000-000000000000"  # valid uuid, no transcript


class _Exec(Exception):
    """Raised by the fake execvp to unwind out of main() without replacing us."""


def run_main(decision, sid):
    """Call cr.main() for `sid` with announce_decision forced to `decision` and
    execvp stubbed; return the (file, argv) execvp was called with, else None.

    stdin/stdout are swapped for StringIO so the un-wired main() can't block on
    input() and render() can't scribble on the test's terminal."""
    calls = []
    saved = (cr.announce_decision, cr.os.execvp, cr.sys.argv,
             cr.sys.stdout, cr.sys.stdin)
    try:
        cr.announce_decision = lambda *a, **k: decision

        def fake_execvp(file, argv):
            calls.append((file, list(argv)))
            raise _Exec

        cr.os.execvp = fake_execvp
        cr.sys.argv = ["claude-resume", sid]
        cr.sys.stdout = io.StringIO()
        cr.sys.stdin = io.StringIO()
        try:
            cr.main()
        except (_Exec, SystemExit):
            pass
    finally:
        (cr.announce_decision, cr.os.execvp, cr.sys.argv,
         cr.sys.stdout, cr.sys.stdin) = saved
    return calls[0] if calls else None


def test_main_skip_does_not_exec():
    assert run_main("skip", FAKE_SID) is None, "skip must not exec claude"


def test_main_resume_execs_claude_resume():
    call = run_main("resume", FAKE_SID)
    assert call == ("claude", ["claude", "--resume", FAKE_SID]), f"got {call!r}"


def main():
    cases = [
        ("enter_resumes_and_announces_session", test_enter_resumes_and_announces_session),
        ("ctrl_c_skips_and_announces", test_ctrl_c_skips_and_announces),
        ("ctrl_d_skips_and_announces", test_ctrl_d_skips_and_announces),
        ("non_tty_resumes_without_reading", test_non_tty_resumes_without_reading),
        ("no_sid_announces_picker", test_no_sid_announces_picker),
        ("main_skip_does_not_exec", test_main_skip_does_not_exec),
        ("main_resume_execs_claude_resume", test_main_resume_execs_claude_resume),
    ]
    ok = all(case(n, f) for n, f in cases)
    print("PASS" if ok else "FAILED")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
