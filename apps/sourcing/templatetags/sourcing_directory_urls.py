"""Canonical querystring changes for Sourcing directory GET links.

Preserve current filters while replacing status/page exactly once.  GET links
must work with JavaScript disabled and not contain stale/duplicate parameters.
"""
from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def sourcing_directory_url(context, *, query_only=False, **updates):
    request = context.get("request")
    if request is None:
        raise ValueError("Sourcing directory links require the request context processor")
    params = request.GET.copy()
    for key in ("view", "fragment", "provider", "cap_page", "unified"):
        params.pop(key, None)
    for key, value in updates.items():
        if value is None or value == "":
            params.pop(key, None)
        else:
            # Single value, never append to a pre-existing GET parameter.
            params.setlist(key, [str(value)])
    query = params.urlencode()
    # Directory navigation links need a path when no filters are set, whereas
    # exports append this result after an independently reversed endpoint.
    # Appending request.path to an export endpoint creates a broken URL such as
    # /vendors/export/pdf/app/sourcing/vendors/ on a clean directory page.
    return "?" + query if query else ("" if query_only else request.path)
