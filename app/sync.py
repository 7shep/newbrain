"""Keeps the notes folder in step with its GitHub repo, for the phone app (docs/specs/2026-09-27-phone-app.md).

On only when the notes folder is a git repo with a phone/ folder. Pulls when Brain starts, when the page
asks for fresh state, and every minute in the background so phone agent tasks start with no tab open (at most
once a minute either way). Commits only the files Brain itself wrote, then pushes in the
background. A pull that can't rebase cleanly is aborted and reported, never auto-resolved. The one exception is a
note that both sides created with identical contents (e.g. today's daily tasks): the untracked local copy is dropped.
"""
import os
import subprocess
import threading
import time

GAP = 60  # seconds between pulls triggered by page loads or the background timer


class Sync:
    def __init__(self, notes, on_pulled=None):
        self.notes = notes
        self.on_pulled = on_pulled or (lambda: None)
        self.last = 0.0
        self.error = None
        self.lock = threading.Lock()
        self.stopped = threading.Event()

    def start(self, every=GAP):
        """Pull every `every` seconds on a daemon thread, so a phone agent task starts while no Brain tab is open."""
        def loop():
            while not self.stopped.wait(every):
                try:
                    self.pull()
                except Exception as e:  # never let one bad pull end the timer
                    self.error = "Background sync failed: %s" % e
        threading.Thread(target=loop, daemon=True).start()

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
                if not self._settle_index():  # a stuck half-merge would make every later pull fail
                    return False
                p = self._pull()
            except subprocess.TimeoutExpired:
                self.error = "Pull timed out. Offline?"
                return False
            if p.returncode != 0:
                self._git("rebase", "--abort")  # leave the folder exactly as it was
                msg = (p.stderr or p.stdout).strip().splitlines()
                self.error = "Sync paused: " + (msg[-1] if msg else "git pull failed") + ". Fix it in a terminal or ask Claude."
                return False
            if not self._settle_index():  # the autostash can clash with what was just pulled
                return False
            self.error = None
            ahead = self._git("rev-list", "--count", "@{u}..HEAD").stdout.strip()
        if ahead not in ("", "0"):  # commits a failed push left behind would otherwise wait for the next change
            threading.Thread(target=self.push, daemon=True).start()
        self.on_pulled()
        return True

    def _pull(self):
        """git pull --rebase --autostash, getting past untracked notes the pull would overwrite. The autostash leaves
        untracked files alone, so one the Mac wrote but never committed (and GitHub has too) blocks every pull. Drop
        each local copy that matches the pulled one byte for byte and retry; if any differs, leave all of them."""
        p = self._git("pull", "--rebase", "--autostash", "--quiet")
        if p.returncode == 0 or "untracked working tree files would be overwritten" not in p.stderr + p.stdout:
            return p
        self._git("rebase", "--abort")
        untracked = subprocess.run(["git", "-C", self.notes, "ls-files", "--others", "--exclude-standard", "-z"],
                                   capture_output=True, timeout=30).stdout.decode("utf-8", "replace").split("\0")
        same, differ = [], []
        for rel in filter(None, untracked):
            theirs = subprocess.run(["git", "-C", self.notes, "show", "@{u}:" + rel], capture_output=True, timeout=30)
            if theirs.returncode != 0:
                continue  # not in the pull: no clash
            with open(os.path.join(self.notes, rel), "rb") as f:
                mine = f.read()
            (same if mine.replace(b"\r\n", b"\n") == theirs.stdout.replace(b"\r\n", b"\n") else differ).append(rel)
        if differ:
            p.stderr = "%s differ from GitHub's copies (untracked here)" % ", ".join(differ)
            return p
        for rel in same:
            os.remove(os.path.join(self.notes, rel))
        return self._git("pull", "--rebase", "--autostash", "--quiet")

    def _settle_index(self):
        """Clear a conflict left by restoring the autostash. INDEX.md is generated, so take the pulled copy (Brain
        rebuilds it, and git keeps the stash); any other conflicted note is reported, never auto-resolved."""
        stuck = self._git("diff", "--name-only", "--diff-filter=U").stdout.split()
        if not stuck:
            return True
        if stuck == ["INDEX.md"]:
            self._git("checkout", "HEAD", "--", "INDEX.md")
            return True
        self.error = "Sync paused: unresolved changes in " + ", ".join(stuck) + ". Fix it in a terminal or ask Claude."
        return False

    def snapshot(self):
        """{path: blob hash} for every changed or untracked notes file right now ({} when sync is off). Taken before
        and after something runs, it tells which files that run touched (changed_since), leaving earlier edits alone."""
        if not self.enabled():
            return {}
        run = lambda *args, **kw: subprocess.run(["git", "-C", self.notes, *args], capture_output=True,
                                                  encoding="utf-8", errors="replace", timeout=30, **kw)
        entries, paths = run("status", "--porcelain", "-z", "--untracked-files=all").stdout.split("\0"), []
        skip = False
        for e in entries:
            if skip or len(e) < 4:  # a rename's second entry is its old path
                skip = False
                continue
            skip = "R" in e[:2] or "C" in e[:2]
            paths.append(e[3:])
        present = [p for p in paths if os.path.isfile(os.path.join(self.notes, p))]
        hashes = run("hash-object", "--stdin-paths", input="\n".join(present)).stdout.split() if present else []
        out = dict.fromkeys(paths)  # a deleted file hashes to None
        out.update(zip(present, hashes))
        return out

    def changed_since(self, before):
        """Paths whose state differs from the snapshot `before`: new, edited again, or deleted since."""
        now = self.snapshot()
        return sorted(p for p in set(now) | set(before) if now.get(p, "clean") != before.get(p, "clean"))

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
                    p = self._pull()
                except subprocess.TimeoutExpired:
                    self.error = "Push timed out. Offline? It will retry on the next change."
                    return False
                if p.returncode != 0:
                    self._git("rebase", "--abort")
                    self.error = "Sync paused: your Mac and GitHub both changed the same note. Fix it in a terminal or ask Claude."
                    return False
            self.error = "Push kept failing. It will retry on the next change."
            return False
