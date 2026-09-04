from django import forms

from .models import PendingAction, Task


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = [
            "title",
            "description",
            "status",
            "priority",
            "priority_reason",
            "due_date",
            "estimated_minutes",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "field-control",
                    "placeholder": "Name the work",
                    "autocomplete": "off",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "field-control field-area",
                    "rows": 4,
                    "placeholder": "What does done look like?",
                }
            ),
            "status": forms.Select(attrs={"class": "field-control"}),
            "priority": forms.Select(attrs={"class": "field-control"}),
            "priority_reason": forms.TextInput(
                attrs={
                    "class": "field-control",
                    "placeholder": "Why this rank, in one line",
                }
            ),
            "due_date": forms.DateInput(
                attrs={"class": "field-control", "type": "date"}
            ),
            "estimated_minutes": forms.NumberInput(
                attrs={
                    "class": "field-control",
                    "min": "1",
                    "step": "5",
                }
            ),
        }


class ActionDraftForm(forms.ModelForm):
    class Meta:
        model = PendingAction
        fields = ["draft_content"]
        widgets = {
            "draft_content": forms.Textarea(
                attrs={
                    "class": "field-control field-area field-area-lg",
                    "rows": 8,
                }
            ),
        }


class ActionTypeForm(forms.Form):
    action_type = forms.ChoiceField(
        choices=PendingAction.ACTION_TYPES,
        widget=forms.Select(attrs={"class": "field-control"}),
    )