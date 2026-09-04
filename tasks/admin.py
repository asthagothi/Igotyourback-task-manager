from django.contrib import admin

from .models import PendingAction, Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "status",
        "priority",
        "priority_reason",
        "due_date",
        "updated_at",
    )
    list_filter = ("status", "priority")
    search_fields = ("title", "description", "priority_reason")


@admin.register(PendingAction)
class PendingActionAdmin(admin.ModelAdmin):
    list_display = ("action_type", "task", "status", "created_at", "executed_at")
    list_filter = ("action_type", "status")
    search_fields = ("draft_content", "execution_log", "task__title")
    readonly_fields = ("execution_log", "executed_at")