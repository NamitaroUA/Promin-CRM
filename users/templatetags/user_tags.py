from django import template

register = template.Library()

@register.filter
def is_teacher(user):
    return getattr(user, "role", None) == "teacher"