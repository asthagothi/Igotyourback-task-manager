from django.conf import settings

from .models import PendingAction, Task


def chrome(request):
    match = getattr(request, "resolver_match", None)
    url_name = getattr(match, "url_name", "") or ""

    try:
        pending = Task.objects.filter(status="pending").exists()
        active = Task.objects.filter(status="in_progress").exists()
        done = Task.objects.filter(status="completed").exists()
        waiting_actions = PendingAction.objects.filter(status="pending").count()
    except Exception:
        pending = active = done = False
        waiting_actions = 0

    if active:
        phase = "now"
    elif pending:
        phase = "next"
    elif done:
        phase = "done"
    else:
        phase = "plan"

    return {
        "nav": url_name,
        "css_version": settings.CSS_VERSION,
        "spine_phase": phase,
        "waiting_actions": waiting_actions,
    }