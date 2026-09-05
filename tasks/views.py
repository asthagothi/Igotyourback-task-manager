import json
import logging

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from datetime import date

from .ai_service import (
    build_daily_plan,
    draft_action_content,
    generate_task_plan,
    get_active_tasks,
)
from .email_service import EmailDraftError, set_to_line
from .forms import ActionDraftForm, ActionTypeForm, TaskForm
from .models import PendingAction, Task

logger = logging.getLogger(__name__)


def _desk_counts():
    qs = Task.objects.all()
    return {
        "total_tasks": qs.count(),
        "pending_tasks": qs.filter(status="pending").count(),
        "in_progress_tasks": qs.filter(status="in_progress").count(),
        "completed_tasks": qs.filter(status="completed").count(),
    }


def _spine_phase(counts):
    if counts["in_progress_tasks"]:
        return "now"
    if counts["pending_tasks"]:
        return "next"
    if counts["completed_tasks"]:
        return "done"
    return "plan"


def _create_calendar_draft(task):
    existing = PendingAction.objects.filter(
        task=task,
        action_type="calendar",
        status="pending",
    ).exists()
    if existing:
        return None
    return PendingAction.objects.create(
        task=task,
        action_type="calendar",
        draft_content=draft_action_content(task, "calendar"),
        status="pending",
    )


def dashboard(request):
    search = request.GET.get("search", "").strip()
    selected_status = request.GET.get("status", "")
    selected_priority = request.GET.get("priority", "")

    tasks = Task.objects.all()
    if search:
        tasks = tasks.filter(
            Q(title__icontains=search) | Q(description__icontains=search)
        )
    if selected_status:
        tasks = tasks.filter(status=selected_status)
    if selected_priority:
        tasks = tasks.filter(priority=selected_priority)

    counts = _desk_counts()
    day_items, day_minutes = build_daily_plan()
    context = {
        **counts,
        "day_items": day_items,
        "day_minutes": day_minutes,
        "tasks": tasks,
        "pending_list": tasks.filter(status="pending"),
        "progress_list": tasks.filter(status="in_progress"),
        "completed_list": tasks.filter(status="completed"),
        "search": search,
        "selected_status": selected_status,
        "selected_priority": selected_priority,
        "is_filtered": bool(search or selected_status or selected_priority),
        "spine_phase": _spine_phase(counts),
        "pending_actions": PendingAction.objects.filter(
            status="pending"
        ).select_related("task"),
        "action_type_form": ActionTypeForm(),
    }
    return render(request, "dashboard.html", context)


def add_task(request):
    if request.method == "POST":
        form = TaskForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Task added to your desk.")
            return redirect("dashboard")
    else:
        form = TaskForm()

    return render(
        request,
        "task_form.html",
        {"form": form, "edit_mode": False},
    )


def edit_task(request, task_id):
    task = get_object_or_404(Task, pk=task_id)
    if request.method == "POST":
        form = TaskForm(request.POST, instance=task)
        if form.is_valid():
            form.save()
            messages.success(request, "Changes saved.")
            return redirect("dashboard")
    else:
        form = TaskForm(instance=task)

    return render(
        request,
        "task_form.html",
        {"form": form, "edit_mode": True, "task": task},
    )


def delete_task(request, task_id):
    task = get_object_or_404(Task, pk=task_id)
    if request.method == "POST":
        task.delete()
        messages.success(request, "Task removed.")
        return redirect("dashboard")
    return render(request, "delete_confirm.html", {"task": task})


def complete_task(request, task_id):
    task = get_object_or_404(Task, pk=task_id)
    task.status = "completed"
    task.save(update_fields=["status", "updated_at"])
    messages.success(request, "Task completed.")
    return redirect("dashboard")


def start_task(request, task_id):
    task = get_object_or_404(Task, pk=task_id)
    task.status = "in_progress"
    task.save(update_fields=["status", "updated_at"])
    messages.success(request, "Task is in progress.")
    return redirect("dashboard")


def _planned_from_post(request):
    raw = (request.POST.get("tasks_json") or "").strip()
    if not raw:
        return request.session.get("ai_tasks") or []
    try:
        planned = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Could not parse posted AI tasks.")
        return request.session.get("ai_tasks") or []
    if not isinstance(planned, list):
        return []
    return planned


def ai_assistant(request):
    tasks = None
    error = None
    prompt = ""
    active_tasks = get_active_tasks()

    if request.method == "POST":
        prompt = (
            request.POST.get("prompt")
            or request.POST.get("goal")
            or ""
        ).strip()
        if not prompt:
            error = "Describe the goal before generating a plan."
        else:
            try:
                tasks = generate_task_plan(prompt, active_tasks=active_tasks)
                request.session["ai_tasks"] = tasks
                request.session["ai_goal"] = prompt
                request.session.modified = True
            except Exception:
                logger.exception("Planner failed.")
                error = (
                    "The plan could not be generated. "
                    "Check GEMINI_API_KEY in .env, or try again."
                )

    elif request.session.get("ai_tasks"):
        tasks = request.session.get("ai_tasks")
        prompt = request.session.get("ai_goal", "")

    return render(
        request,
        "ai_assistant.html",
        {
            "tasks": tasks,
            "tasks_json": json.dumps(tasks or []),
            "error": error,
            "prompt": prompt,
            "active_tasks": active_tasks,
        },
    )


def save_ai_tasks(request):
    if request.method != "POST":
        return redirect("ai_assistant")

    planned = _planned_from_post(request)
    if not planned:
        messages.error(request, "Generate a plan before adding it to the desk.")
        return redirect("ai_assistant")

    created = []
    for item in planned:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "Untitled task").strip()[:200]
        if not title:
            continue
        try:
            minutes = int(item.get("estimated_minutes") or 30)
        except (TypeError, ValueError):
            minutes = 30
        priority = str(item.get("priority") or "medium").lower()
        if priority not in {"low", "medium", "high"}:
            priority = "medium"
        reason = str(
            item.get("priority_reason") or item.get("reason") or ""
        ).strip()[:180]
        due = None
        raw_due = str(item.get("due_date") or "").strip()[:10]
        if raw_due:
            try:
                due = date.fromisoformat(raw_due)
            except ValueError:
                due = None
        created.append(
            Task.objects.create(
                title=title,
                description=item.get("description") or "",
                priority=priority,
                priority_reason=reason,
                estimated_minutes=max(1, minutes),
                due_date=due,
                status="pending",
            )
        )

    request.session.pop("ai_tasks", None)
    request.session.pop("ai_goal", None)

    if not created:
        messages.error(request, "No tasks could be saved from that plan.")
        return redirect("dashboard")

    high = next((task for task in created if task.priority == "high"), created[0])
    draft = _create_calendar_draft(high)
    if draft:
        messages.success(
            request,
            f"{len(created)} tasks added to your desk. "
            f"A calendar draft is waiting for {high.title} — nothing was sent.",
        )
    else:
        messages.success(request, f"{len(created)} tasks added to your desk.")
    return redirect("dashboard")


def plan_my_day(request):
    items, minutes = build_daily_plan()
    if request.method == "POST":
        if not items:
            messages.info(request, "Nothing open to plan. Add a task or generate a plan.")
            return redirect("ai_assistant")
        first = get_object_or_404(Task, pk=items[0]["id"])
        if first.status == "pending":
            first.status = "in_progress"
            first.save(update_fields=["status", "updated_at"])
            messages.success(
                request,
                f"Day accepted. Started: {first.title}. The rest stay in To do, in this order.",
            )
        else:
            messages.success(
                request,
                f"Day accepted. Keep going on: {first.title}.",
            )
        return redirect("dashboard")

    return render(
        request,
        "day_plan.html",
        {
            "day_items": items,
            "day_minutes": minutes,
            "active_tasks": get_active_tasks(),
        },
    )


@require_POST
def draft_action(request, task_id):
    task = get_object_or_404(Task, pk=task_id)
    form = ActionTypeForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose calendar or email.")
        return redirect("dashboard")

    action_type = form.cleaned_data["action_type"]
    existing = PendingAction.objects.filter(
        task=task,
        action_type=action_type,
        status="pending",
    ).exists()
    if existing:
        messages.info(request, f"A {action_type} draft is already waiting for this task.")
        return redirect("dashboard")

    PendingAction.objects.create(
        task=task,
        action_type=action_type,
        draft_content=draft_action_content(task, action_type),
        status="pending",
    )
    messages.success(
        request,
        f"{action_type.title()} draft ready. Nothing sent — approve it when it looks right.",
    )
    return redirect("dashboard")


def edit_action(request, action_id):
    action = get_object_or_404(PendingAction, pk=action_id)
    if action.status != "pending":
        messages.error(request, "Only waiting drafts can be edited.")
        return redirect("dashboard")

    if request.method == "POST":
        content = (request.POST.get("draft_content") or "").strip()
        recipient = (request.POST.get("to_email") or "").strip()
        if recipient:
            content = set_to_line(content or action.draft_content, recipient)
        if not content:
            messages.error(request, "The draft cannot be empty.")
        else:
            action.draft_content = content
            action.save(update_fields=["draft_content", "updated_at"])
            messages.success(request, "Draft updated. Still waiting for your approve.")
            return redirect("dashboard")

    return render(request, "action_form.html", {"action": action})


@require_POST
def approve_action(request, action_id):
    action = get_object_or_404(PendingAction, pk=action_id)
    if action.status != "pending":
        messages.error(request, "This draft is no longer waiting.")
        return redirect("dashboard")

    recipient = (request.POST.get("to_email") or "").strip()
    if recipient:
        action.draft_content = set_to_line(action.draft_content, recipient)
        action.save(update_fields=["draft_content", "updated_at"])

    try:
        action.execute()
    except EmailDraftError as exc:
        messages.error(request, str(exc))
        return redirect("dashboard")
    except Exception:
        logger.exception("Approve failed.")
        messages.error(request, "Approve failed. The draft is still waiting.")
        return redirect("dashboard")

    if action.action_type == "email":
        messages.success(
            request,
            "Approved. Email handed to Django. "
            "On the console backend it prints in the runserver terminal — nothing leaves the machine.",
        )
    else:
        messages.success(request, "Approved. Logged the intended call — nothing was sent.")
    return redirect("dashboard")


@require_POST
def reject_action(request, action_id):
    action = get_object_or_404(PendingAction, pk=action_id)
    if action.status != "pending":
        messages.error(request, "This draft is no longer waiting.")
        return redirect("dashboard")
    action.status = "rejected"
    action.save(update_fields=["status", "updated_at"])
    messages.info(request, "Rejected. No call was logged.")
    return redirect("dashboard")