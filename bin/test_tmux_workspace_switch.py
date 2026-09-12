#!/usr/bin/env python3
"""End-to-end tests for tmux-workspace-switch, on an isolated tmux server.

Spawns REAL attached clients on pseudo-terminals (pty.fork + exec tmux),
because everything under test is about per-client behaviour: independent
current-windows across grouped clones, destroy-unattached reaping, and the
prefix+s choose-tree binding's template expansion (%% and #{client_name}).

Tests are numbered: they tell one story (fresh logins -> workspace hops ->
repair -> binding), and each builds on the state the previous one left.

stdlib-only; run with:  uv run python bin/test_tmux_workspace_switch.py
"""
import os
import pty
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HELPER = os.path.join(HERE, "tmux-workspace-switch")

FILTER = ("#{||:#{==:#{session_group},},"
          "#{==:#{session_name},#{session_group}}}")

# The exact binding under test (kept in sync with tmux/tmux.conf by
# test_00_binding_matches_tmux_conf).
BIND_LINE = (
    "bind s choose-tree -Zs -f '%s' "
    '"run-shell -b \\"%s \'%%%%\' \'#{client_name}\'\\""' % (FILTER, HELPER)
)


def wait_for(pred, what, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return
        time.sleep(0.05)
    raise AssertionError("timed out waiting for " + what)


class Client:
    """A real tmux client attached on a pty (its own grouped clone of sess)."""

    def __init__(self, sock, sess):
        env = {k: v for k, v in os.environ.items() if k != "TMUX"}
        env["TERM"] = "xterm-256color"
        pid, fd = pty.fork()
        if pid == 0:  # child
            os.execvpe("tmux", ["tmux", "-S", sock,
                                "new-session", "-t", sess, ";",
                                "set-option", "destroy-unattached",
                                "keep-last"], env)
        self.pid, self.fd = pid, fd
        self.name = None  # /dev/pts/N, filled in by setUpClass
        # Drain continuously so tmux never blocks writing to the client.
        threading.Thread(target=self._drain, daemon=True).start()

    def _drain(self):
        try:
            while True:
                if not os.read(self.fd, 4096):
                    return
        except OSError:
            return

    def send(self, data):
        os.write(self.fd, data.encode())

    def close(self):
        try:
            os.kill(self.pid, signal.SIGHUP)
        except ProcessLookupError:
            pass


class Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory(prefix="tws-test-")
        cls.sock = os.path.join(cls.dir.name, "sock")
        conf = os.path.join(cls.dir.name, "tmux.conf")
        with open(conf, "w") as f:
            f.write(BIND_LINE + "\n")
        cls.t("-f", conf, "new-session", "-d", "-s", "A", "-x80", "-y24")
        for _ in range(5):
            cls.t("new-window", "-t", "A")
        cls.t("new-session", "-d", "-s", "B", "-x80", "-y24")
        cls.t("new-window", "-t", "B")
        cls.t("new-window", "-t", "B")
        # Attach one client at a time so pty <-> client_name is unambiguous.
        cls.c1 = Client(cls.sock, "A")
        wait_for(lambda: len(cls.clients()) == 1, "client 1 attached")
        cls.c1.name = next(iter(cls.clients()))
        cls.c2 = Client(cls.sock, "A")
        wait_for(lambda: len(cls.clients()) == 2, "client 2 attached")
        cls.c2.name = (set(cls.clients()) - {cls.c1.name}).pop()

    @classmethod
    def tearDownClass(cls):
        cls.c1.close()
        cls.c2.close()
        subprocess.run(["tmux", "-S", cls.sock, "kill-server"],
                       capture_output=True)
        cls.dir.cleanup()

    @classmethod
    def t(cls, *args):
        return subprocess.run(["tmux", "-S", cls.sock] + list(args),
                              check=True, capture_output=True,
                              text=True).stdout

    @classmethod
    def clients(cls):
        out = cls.t("list-clients", "-F",
                    "#{client_name}\t#{client_session}")
        return dict(line.split("\t") for line in out.splitlines())

    @classmethod
    def sessions(cls):
        out = cls.t("list-sessions", "-F",
                    "#{session_name}\t#{session_group}\t"
                    "#{window_index}\t#{destroy-unattached}")
        return {r[0]: r[1:] for r in
                (line.split("\t") for line in out.splitlines())}

    def run_helper(self, target, client):
        env = dict(os.environ, TMUX=self.sock + ",0,0")
        r = subprocess.run([HELPER, target, client], env=env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_00_binding_matches_tmux_conf(self):
        # The BIND_LINE this file tests must be the one tmux.conf ships
        # (modulo the helper's path, which tmux.conf takes from ~/bin).
        with open(os.path.join(HERE, os.pardir, "tmux", "tmux.conf")) as f:
            conf = f.read()
        expect = BIND_LINE.replace(HELPER, "~/bin/tmux-workspace-switch")
        self.assertIn(expect, conf,
                      "tmux/tmux.conf bind s drifted from the tested line")

    def test_01_clones_have_independent_current_windows(self):
        s1, s2 = self.clients()[self.c1.name], self.clients()[self.c2.name]
        self.assertNotEqual(s1, s2, "each login must get its own clone")
        self.t("select-window", "-t", f"{s1}:5")
        self.t("select-window", "-t", f"{s2}:1")
        self.assertEqual(self.sessions()[s1][1], "5")
        self.assertEqual(self.sessions()[s2][1], "1",
                         "client 2 must not follow client 1's switch")

    def test_02_switch_to_other_workspace_gets_fresh_clone(self):
        old = self.clients()[self.c1.name]
        self.run_helper("=B", self.c1.name)
        wait_for(lambda: old not in self.sessions(),
                 "old clone reaped by destroy-unattached")
        new = self.clients()[self.c1.name]
        group, _win, destroy = self.sessions()[new]
        self.assertEqual(group, "B", "clone must join B's group")
        self.assertNotEqual(new, "B", "must never land on the base")
        self.assertEqual(destroy, "keep-last")
        self.assertIn("B", self.sessions(), "B's base must survive")
        self.assertEqual(self.sessions()[self.clients()[self.c2.name]][0],
                         "A", "other client must be untouched")

    def test_03_window_target_selects_window_in_clone(self):
        self.run_helper("=B:2", self.c2.name)
        new = self.clients()[self.c2.name]
        self.assertEqual(self.sessions()[new][:2], ["B", "2"])

    def test_04_same_group_selects_in_place(self):
        before = self.clients()[self.c2.name]
        self.run_helper("=B:0", self.c2.name)
        self.assertEqual(self.clients()[self.c2.name], before,
                         "same-group switch must not create a new clone")
        self.assertEqual(self.sessions()[before][1], "0")

    def test_05_client_parked_on_base_is_repaired(self):
        # Park c2 directly on the base (the pre-fix failure mode).
        self.t("switch-client", "-c", self.c2.name, "-t", "B")
        wait_for(lambda: self.clients()[self.c2.name] == "B",
                 "c2 parked on base")
        self.run_helper("=B", self.c2.name)
        new = self.clients()[self.c2.name]
        self.assertNotEqual(new, "B", "repair must move client off base")
        self.assertEqual(self.sessions()[new][0], "B")

    def test_06_binding_end_to_end(self):
        # Drive the real prefix+s binding: the template must expand %% and
        # #{client_name}. c1 sits on a B clone; the filtered tree shows
        # A and B, cursor on the first item (its own clone is hidden), so
        # Enter selects A -> c1 must land on a fresh A clone.
        before = self.clients()[self.c1.name]
        self.c1.send("\x02s")          # prefix+s -> choose-tree
        time.sleep(0.8)
        self.c1.send("\r")             # select first (topmost) item: A
        wait_for(lambda: self.clients().get(self.c1.name) != before,
                 "binding switched c1 to a new session")
        now = self.clients()[self.c1.name]
        group, _win, destroy = self.sessions()[now]
        self.assertEqual(group, "A", "binding must land on an A-group clone")
        self.assertNotEqual(now, "A", "binding must not land on the base")
        self.assertEqual(destroy, "keep-last")

    def test_07_choose_tree_filter_hides_clones(self):
        # Evaluate the bind's -f filter per session: 1 (shown) for canonical
        # sessions, 0 (hidden) for per-login clones. (capture-pane shows the
        # pane under the choose-tree overlay, not the tree itself, so the
        # filter expression is the directly testable part.)
        sess = self.sessions()
        self.assertTrue(any(g and n != g for n, (g, _w, _d) in sess.items()),
                        "test needs at least one live clone to be meaningful")
        for name, (group, _win, _destroy) in sess.items():
            shown = self.t("display-message", "-p", "-t", name,
                           FILTER).strip()
            want = "1" if (not group or name == group) else "0"
            self.assertEqual(shown, want, f"filter for {name}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
