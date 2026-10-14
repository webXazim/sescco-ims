"""Readable tenant-scoped provider identifiers shared by new provider forms."""
from django.core.exceptions import ValidationError
from django.utils.text import slugify


def next_provider_code(*, prefix, name='', company=None, model=None):
    base = prefix + '-' + (slugify(str(name or '').strip(), allow_unicode=True).upper()[:26].rstrip('-') or 'UNNAMED')
    if company is None or model is None:
        return base
    used = model.objects.for_company(company)
    for index in range(1, 100001):
        suffix = '' if index == 1 else f'-{index}'
        code = base[:30 - len(suffix)].rstrip('-') + suffix
        if not used.filter(code__iexact=code).exists():
            return code
    raise ValidationError({'code': 'Unable to allocate a unique provider code.'})
