from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def query_params(context, **updates):
    query = context["request"].GET.copy()
    for key, value in updates.items():
        if value in (None, ""):
            query.pop(key, None)
        else:
            query[key] = value
    return query.urlencode()


@register.simple_tag(takes_context=True)
def pagination_url(context, page_number, page_param="page"):
    """Keep the active filters while changing a paginator's page parameter."""
    query = context["request"].GET.copy()
    query[page_param] = page_number
    return query.urlencode()
