"""Keeps the notes folder in step with its GitHub repo, for the phone app (docs/specs/2026-09-27-phone-app.md).

On only when the notes folder is a git repo with a phone/ folder. Pulls when Brain starts and when the page
asks for fresh state (at most once a minute). Commits only the files Brain itself wrote, then pushes in the
background. A pull that can't rebase cleanly is aborted and reported, never auto-resolved.
"""
import os
import subprocess
import threading
import time

GAP = 60  # seconds between pulls triggered by page loads


class Sync:
    def __init__(self, notes, on_pulled=None):
        self.notes = notes
        self.on_pulled = on_pulled or (lambda: None)
        self.last = 0.0
        self.error = None
        self.lock = threading.Lock()

    def enabled(self):
        return os.path.isdir(os.path.join(self.notes, "phone")) and os.path.isdir(os.path.join(self.notes, ".git"))

    def _git(self, *args, timeout=30):
        return subprocess.run(["git", "-C", self.notes, *args], capture_output=True, text=True, timeout=timeout)

    def pull(self, gap=GAP):
        """Returns True if it pulled cleanly (or had nothing to do)."""
        if not self.enabled() or time.time() - self.last < gap:
            return True
        with self.lock:
            self.last = time.time()
            try:
                p = self._git("pull", "--rebase", "--autostash", "--quiet")
            except subprocess.TimeoutExpired:
                self.error = "Pull timed out. Offline?"
                return False
            if p.returncode != 0:
                self._git("rebase", "--abort")  # leave the folder exactly as it was
                msg = (p.stderr or p.stdout).strip().splitlines()
                self.error = "Sync paused: " + (msg[-1] if msg else "git pull failed") + ". Fix it in a terminal or ask Claude."
                return False
            self.error = None
        self.on_pulled()
        return True

    def commit(self, files, message):
        """Commit just these notes files (paths relative to the notes folder), then push in the background."""
        files = sorted({f for f in files if f and os.path.exists(os.path.join(self.notes, f))})
        if not self.enabled() or not files:
            return
        with self.lock:
            self._git("add", "--", *files)
            if self._git("diff", "--cached", "--quiet", "--", *files).returncode == 0:
                return  # nothing actually changed
            self._git("commit", "--quiet", "-m", message, "--", *files)
        threading.Thread(target=self.push, daemon=True).start()

    def push(self):
        with self.lock:
            for _ in range(3):
                try:
                    if self._git("push", "--quiet").returncode == 0:
                        return True
                    # Rejected: the phone (or GitHub) pushed first. Take theirs, replay ours, try again.
                    p = self._git("pull", "--rebase", "--autostash", "--quiet")
                except subprocess.TimeoutExpired:
                    self.error = "Push timed out. Offline? It will retry on the next change."
                    return False
                if p.returncode != 0:
                    self._git("rebase", "--abort")
                    self.error = "Sync paused: your Mac and GitHub both changed the same note. Fix it in a terminal or ask Claude."
                    return False
            self.error = "Push kept failing. It will retry on the next change."
            return False
