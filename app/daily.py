"""Daily checklist storage: one Markdown file per local calendar date."""
import re

ROW = re.compile(r"^- \[([ xX])\] (.*?) <!-- task:([a-f0-9]{16}) -->$", re.M)


def parse(text):
    return [{"id": key, "text": title, "done": mark.lower() == "x"}
            for mark, title, key in ROW.findall(text)]


def render(date, tasks):
    return "# Daily tasks — %s\n\n" % date + "".join(
        "- [%s] %s <!-- task:%s -->\n" % ("x" if t["done"] else " ", t["text"], t["id"])
        for t in tasks)


def apply(tasks, body, date):
    """Explicit item operations preserve other clients' changes; add retries are idempotent."""
    if body.get("date") != date:
        raise ValueError("A new day has started. Refresh your daily list and try again.")
    action = body.get("action")
    key = body.get("id")
    if not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{16}", key):
        raise ValueError("Invalid task ID")
    tasks = [dict(t) for t in tasks]
    task = next((t for t in tasks if t["id"] == key), None)
    if action == "add":
        title = body.get("text")
        if not isinstance(title, str):
            raise ValueError("Enter a task")
        title = " ".join(title.split())
        if not title or len(title) > 300:
            raise ValueError("Use 1–300 characters for a task")
        if task:
            if task["text"] != title:
                raise ValueError("Task ID already exists")
        else:
            if len(tasks) >= 100:
                raise ValueError("Your daily list is full (100 tasks)")
            tasks.append({"id": key, "text": title, "done": False})
    elif action == "set":
        if not isinstance(body.get("done"), bool):
            raise ValueError("Task completion must be true or false")
        if task is None:
            raise KeyError(key)
        task["done"] = body["done"]
    elif action == "remove":
        tasks = [t for t in tasks if t["id"] != key]
    else:
        raise ValueError("Unknown daily task action")
    return tasks
