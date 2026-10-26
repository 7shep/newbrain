"""The morning dev log: a short post about recent public commits, written by a headless agent and published to the
GitHub profile README (spec: docs/specs/2026-09-27-headless-agents.md, "Dev log").

On only when the notes have devlog/profile.md with a `Repo: <user>/<user>` line. Facts come from the GitHub API, and
only from public repos, so nothing private can reach the public README. The agent has no tools: its final message is
the post. Brain, not the agent, writes devlog/<date>.md and updates the README between the post markers.
"""
import base64
import datetime
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request

HOUR = 7  # the morning run starts at the first check after this hour
DAYS = 7  # how far back a post looks when there is no earlier post
SHOWN = 3  # posts kept in the README
START, END = "<!-- devlog-posts:start -->", "<!-- devlog-posts:end -->"
SKIP = "SKIP"  # the agent's whole answer when the commits don't add up to a post

PROMPT = (
    "Brain started you headless to write today's entry in Alex's dev log, a little blog on his public GitHub profile "
    "README. Nobody is watching, so you can't ask questions, and you have no tools. Today is {date}.\n\n"
    "Write one short post (2 to 4 sentences, under 90 words) about what he built, from the commits below. First person, "
    "plain and specific, a little dry, like a note to a friend who codes: what changed and why it matters, not a list "
    "of commits. Name projects as they're named below. No headings, emoji, hashtags or links, and no hype words "
    "(excited, thrilled, journey, leverage). Never invent features, numbers, results or plans the commits don't show. "
    "If the commits are only chores or too thin to say anything real, answer exactly SKIP.\n\n"
    "Your final message is the post text and nothing else: no preamble, no quotes.\n\n"
    "Recent posts, so you don't repeat yourself:\n{previous}\n\n"
    "Alex's public commits since the last post, as date repo: subject:\n{commits}"
)


def command():
    return [shutil.which("claude") or "claude", "--setting-sources", "project", "--permission-mode", "dontAsk",
            "--model", "claude-sonnet-5-5", "-p"]


def repo(notes):
    """The profile repo from devlog/profile.md (e.g. 7shep/7shep), or None when the dev log is off."""
    try:
        with open(os.path.join(notes, "devlog", "profile.md"), encoding="utf-8") as f:
            m = re.search(r"^Repo:\s*([\w.-]+/[\w.-]+)\s*$", f.read(), re.M)
    except OSError:
        return None
    return m.group(1) if m else None


def posts(notes):
    """[(date, text)] newest first, from devlog/YYYY-MM-DD.md."""
    folder = os.path.join(notes, "devlog")
    out = []
    for name in sorted(os.listdir(folder), reverse=True) if os.path.isdir(folder) else []:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.md", name):
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                out.append((name[:10], f.read().strip()))
    return out


def due(notes, runs, now=None):
    """Whether the morning run should start: the dev log is on, it's past HOUR, and no post or run exists today."""
    now = now or datetime.datetime.now()
    today = now.date().isoformat()
    if not repo(notes) or now.hour < HOUR:
        return False
    if any(d == today for d, _ in posts(notes)):
        return False
    return not any(r["type"] == "devlog" and r["queued"][:10] == today for r in runs)


# ---------------------------------------------------------------- GitHub

def token():
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"]
    gh = shutil.which("gh")
    if not gh:
        return None
    try:
        p = subprocess.run([gh, "auth", "token"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.strip() or None


def api(path, data=None, method="GET", auth=None):
    req = urllib.request.Request("https://api.github.com" + path, method=method,
                                 data=json.dumps(data).encode() if data is not None else None)
    req.add_header("Accept", "application/vnd.github+json")
    if auth:
        req.add_header("Authorization", "Bearer " + auth)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def commits(user, since, auth=None):
    """'date repo: subject' lines for user's own commits in their public repos since `since` (a date)."""
    stamp = since.isoformat() + "T00:00:00Z"
    lines = []
    for r in api("/users/%s/repos?type=owner&sort=pushed&per_page=100" % user, auth=auth):
        if r["private"] or r["archived"] or r["name"] == user or r["pushed_at"] < stamp:
            continue
        for c in api("/repos/%s/%s/commits?author=%s&since=%s&per_page=100" % (user, r["name"], user, stamp), auth=auth):
            if len(c["parents"]) < 2:
                lines.append("%s %s: %s" % (c["commit"]["author"]["date"][:10], r["name"],
                                            c["commit"]["message"].split("\n", 1)[0].strip()))
    return "\n".join(sorted(lines, reverse=True))


def context(notes):
    """(prompt, None) for today's run, or (None, why) when there's nothing to write about."""
    full = repo(notes)
    if not full:
        return None, "No devlog/profile.md with a Repo: line in these notes."
    earlier = posts(notes)
    since = datetime.date.today() - datetime.timedelta(days=DAYS)
    if earlier:
        since = max(since, datetime.date.fromisoformat(earlier[0][0]))
    found = commits(full.split("/")[0], since, token())
    if not found:
        return None, "No public commits since %s, so no post today." % since
    previous = "\n".join("%s: %s" % p for p in earlier[:SHOWN]) or "(none yet)"
    return PROMPT.format(date=datetime.date.today().isoformat(), previous=previous, commits=found), None


def render(entries):
    return "\n\n".join("**%s** · %s" % (datetime.date.fromisoformat(d).strftime("%b %d").replace(" 0", " "), text)
                       for d, text in entries[:SHOWN])


def splice(readme, body):
    if START not in readme or END not in readme:
        raise ValueError("The profile README has no %s and %s markers." % (START, END))
    head, rest = readme.split(START, 1)
    return "%s%s\n%s\n%s%s" % (head, START, body, END, rest.split(END, 1)[1])


def publish(notes, post, date=None):
    """Save the post as devlog/<date>.md and put the newest posts in the profile README. Returns a line for the report."""
    date = date or datetime.date.today().isoformat()
    post = post.strip()
    if not post or post == SKIP:
        return "Nothing worth a post today, so nothing was published."
    full = repo(notes)
    with open(os.path.join(notes, "devlog", date + ".md"), "w", encoding="utf-8") as f:
        f.write(post + "\n")
    auth = token()
    if not auth:
        return "Saved devlog/%s.md, but couldn't publish: no GITHUB_TOKEN and no signed-in gh." % date
    current = api("/repos/%s/readme" % full, auth=auth)
    text = base64.b64decode(current["content"]).decode("utf-8")
    new = splice(text, render(posts(notes)))
    if new == text:
        return "Saved devlog/%s.md; the README already had it." % date
    api("/repos/%s/contents/%s" % (full, current["path"]), method="PUT", auth=auth, data={
        "message": "devlog: post for %s" % date, "sha": current["sha"],
        "content": base64.b64encode(new.encode("utf-8")).decode("ascii")})
    return "Published to https://github.com/%s and saved devlog/%s.md." % (full, date)
