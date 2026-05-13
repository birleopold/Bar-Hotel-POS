from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Lookup ``mapping[key]`` using string keys (e.g. UUID outlet ids)."""
    if mapping is None or key is None:
        return None
    return mapping.get(str(key))
