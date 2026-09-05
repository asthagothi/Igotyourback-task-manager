from django.urls import path

from .views import (
    add_task,
    ai_assistant,
    approve_action,
    complete_task,
    dashboard,
    delete_task,
    draft_action,
    edit_action,
    edit_task,
    plan_my_day,
    reject_action,
    save_ai_tasks,
    start_task,
)

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("add/", add_task, name="add_task"),
    path("edit/<int:task_id>/", edit_task, name="edit_task"),
    path("delete/<int:task_id>/", delete_task, name="delete_task"),
    path("complete/<int:task_id>/", complete_task, name="complete_task"),
    path("start/<int:task_id>/", start_task, name="start_task"),
    path("ai/", ai_assistant, name="ai_assistant"),
    path("ai/day/", plan_my_day, name="plan_my_day"),
    path("ai/save/", save_ai_tasks, name="save_ai_tasks"),
    path("actions/draft/<int:task_id>/", draft_action, name="draft_action"),
    path("actions/edit/<int:action_id>/", edit_action, name="edit_action"),
    path("actions/approve/<int:action_id>/", approve_action, name="approve_action"),
    path("actions/reject/<int:action_id>/", reject_action, name="reject_action"),
]