"""JSON contract for the shared Inventory/Projects deletion confirmation dialog.

The server remains authoritative: this endpoint describes current eligibility but
never authorizes deletion. Each POST re-evaluates lifecycle policy and permissions.
"""

from django.http import JsonResponse


def is_delete_dialog_request(request):
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        and "application/json" in request.headers.get("Accept", "")
    )


def delete_dialog_response(context, *, status=200):
    return JsonResponse(
        {
            "title": context["page_title"],
            "subtitle": context["page_subtitle"],
            "record_label": context["record_label"],
            "record_type": context["record_type"],
            "retention_days": context["retention_days"],
            "delete_allowed": context["delete_allowed"],
            "effects": list(context["effects"]),
            "blockers": [
                {
                    "message": blocker.message,
                    "count": blocker.count,
                }
                for blocker in context["delete_blockers"]
            ],
            "error": context.get("form_error", ""),
        },
        status=status,
    )
