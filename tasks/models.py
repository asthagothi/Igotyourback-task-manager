from django.db import models
from django.utils import timezone


class Task(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
    ]

    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default="medium",
    )
    priority_reason = models.CharField(max_length=180, blank=True)
    due_date = models.DateField(null=True, blank=True)
    estimated_minutes = models.PositiveIntegerField(default=30)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class PendingAction(models.Model):
    ACTION_TYPES = [
        ("calendar", "Calendar event"),
        ("email", "Email"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending approval"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="actions",
    )
    action_type = models.CharField(max_length=20, choices=ACTION_TYPES)
    draft_content = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )
    execution_log = models.TextField(blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_action_type_display()} for {self.task.title}"

    def execute(self):
        if self.status != "pending":
            return
        stamp = timezone.now()
        if self.action_type == "email":
            from .email_service import send_action_email

            result = send_action_email(self.draft_content)
            self.execution_log = (
                f"[{stamp.isoformat(timespec='seconds')}] "
                f"Email sent via {result['backend']}.\n"
                f"To: {result['to']}\n"
                f"Subject: {result['subject']}\n\n"
                f"{self.draft_content}"
            )
        else:
            self.execution_log = (
                f"[{stamp.isoformat(timespec='seconds')}] "
                f"{self.action_type} API would run with this draft, then log.\n\n"
                f"{self.draft_content}"
            )
        self.status = "approved"
        self.executed_at = stamp
        self.save(
            update_fields=["status", "executed_at", "execution_log", "updated_at"]
        )