import json
import logging
import re

from django.conf import settings
from django.db.models import Case, F, IntegerField, Value, When

from .models import Task

logger = logging.getLogger(__name__)

GEMINI_MODELS = (
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
)

PRIORITY_ORDER = Case(
    When(priority="high", then=Value(0)),
    When(priority="medium", then=Value(1)),
    default=Value(2),
    output_field=IntegerField(),
)


def get_active_tasks():
    return list(
        Task.objects.filter(status__in=["pending", "in_progress"])
        .annotate(_rank=PRIORITY_ORDER)
        .order_by("_rank", F("due_date").asc(nulls_last=True), "id")
    )


def format_load(active):
    if not active:
        return "The desk is clear. No pending or in-progress tasks."
    lines = []
    for task in active:
        due = task.due_date.isoformat() if task.due_date else "no date"
        lines.append(
            f"- [{task.priority.upper()}] {task.title} "
            f"({task.status}, due {due}, {task.estimated_minutes} min)"
        )
    return "\n".join(lines)


def generate_task_plan(goal, client_factory=None, active_tasks=None):
    goal = (goal or "").strip()
    if not goal:
        raise ValueError("Describe the goal before generating a plan.")

    if active_tasks is None:
        active_tasks = get_active_tasks()
    load = format_load(active_tasks)

    if settings.GEMINI_API_KEY:
        try:
            return _from_gemini(goal, load, client_factory=client_factory)
        except Exception:
            logger.exception("Gemini planner failed; using a local plan.")

    return _local_plan(goal, active_tasks)


def draft_action_content(task, action_type="calendar"):
    due = task.due_date.isoformat() if task.due_date else "this week"
    if action_type == "email":
        return (
            f"To: (add recipient)\n"
            f"Subject: {task.title}\n\n"
            f"{task.description or 'Following up on this sitting.'}\n\n"
            f"I have {task.estimated_minutes} minutes blocked. "
            f"Due {due}."
        )
    return (
        f"Event: {task.title}\n"
        f"When: {due}\n"
        f"Duration: {task.estimated_minutes} minutes\n"
        f"Notes: {task.description or 'Hold this sitting as written.'}"
    )


def _from_gemini(goal, load, client_factory=None):
    from google import genai

    factory = client_factory or (
        lambda: genai.Client(api_key=settings.GEMINI_API_KEY)
    )
    client = factory()

    prompt = f"""
You are the planner inside IGotYourBack, a personal productivity desk.

Check current load before proposing new tasks or times.
Do not duplicate work already on the plate.
Slot new work around what is already pending or in progress.

Current load:
{load}

The user wants to accomplish this goal:

{goal}

Break this goal into practical, actionable tasks.

Return ONLY valid JSON.
Do not use markdown.
Do not use code fences.

Return an array containing 3 to 7 task objects.

Each object must contain exactly these fields:

{{
    "title": "Short task title",
    "description": "Brief description of what to do",
    "priority": "low",
    "priority_reason": "one line why this rank, e.g. due in 2 days and blocks other work",
    "estimated_minutes": 30
}}

Always output priority and priority_reason as a pair. Never priority alone.

Priority must be exactly one of:
low
medium
high

estimated_minutes must be an integer.
"""

    last_error = None
    for model in GEMINI_MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
            )
            text = (getattr(response, "text", None) or "").strip()
            if not text:
                raise ValueError("Gemini returned an empty response.")
            tasks = _parse_tasks(text)
            if tasks:
                return tasks
        except Exception as exc:
            last_error = exc
            logger.warning("Gemini model %s failed: %s", model, exc)

    raise RuntimeError("All Gemini models failed") from last_error


def _parse_tasks(text):
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.replace("```", "").strip()

    match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
    if match:
        cleaned = match.group(0)

    tasks = json.loads(cleaned)
    if isinstance(tasks, dict):
        tasks = tasks.get("tasks") or tasks.get("plan") or [tasks]
    if not isinstance(tasks, list):
        raise ValueError("Gemini did not return a list of tasks.")

    normalized = [_normalize(item) for item in tasks]
    normalized = [item for item in normalized if item["title"]]
    if not normalized:
        raise ValueError("Gemini returned no usable tasks.")
    return normalized[:7]


def _normalize(item):
    if not isinstance(item, dict):
        raise ValueError("Each task must be an object.")

    priority = str(item.get("priority", "medium")).lower()
    if priority not in {"low", "medium", "high"}:
        priority = "medium"

    try:
        minutes = int(item.get("estimated_minutes") or 30)
    except (TypeError, ValueError):
        minutes = 30

    title = str(item.get("title") or "Untitled task").strip()[:200]
    description = str(item.get("description") or "").strip()
    reason = str(
        item.get("priority_reason") or item.get("reason") or ""
    ).strip()[:180]

    return {
        "title": title or "Untitled task",
        "description": description,
        "priority": priority,
        "priority_reason": reason,
        "estimated_minutes": max(1, minutes),
    }


def _local_plan(goal, active_tasks=None):
    short = goal if len(goal) < 72 else f"{goal[:69].rstrip()}…"
    load = active_tasks or []
    high_open = sum(1 for task in load if task.priority == "high")
    if high_open:
        first_reason = f"{high_open} high items already open — keep this short"
        later_reason = "slots after the work already on the plate"
    else:
        first_reason = "unblocks the rest of this goal"
        later_reason = "can wait until the first sitting lands"

    return [
        {
            "title": f"Clarify the outcome for: {short}",
            "description": f"Write one sentence for what done means: {goal}",
            "priority": "high",
            "priority_reason": first_reason,
            "estimated_minutes": 20,
        },
        {
            "title": "List the constraints",
            "description": "Note the deadline, available hours, and the current load.",
            "priority": "medium",
            "priority_reason": later_reason,
            "estimated_minutes": 15,
        },
        {
            "title": f"Break this into sittings: {short}",
            "description": "Split the goal into 3–5 sittings you can finish in one pass each.",
            "priority": "high",
            "priority_reason": first_reason,
            "estimated_minutes": 30,
        },
        {
            "title": "Do the first sitting",
            "description": f"Start the smallest piece that unblocks the rest of: {short}",
            "priority": "high",
            "priority_reason": "this is the sitting that moves the pile",
            "estimated_minutes": 45,
        },
        {
            "title": "Review and close",
            "description": "Check the outcome sentence. Keep leftover work as its own task or drop it.",
            "priority": "medium",
            "priority_reason": later_reason,
            "estimated_minutes": 20,
        },
    ]