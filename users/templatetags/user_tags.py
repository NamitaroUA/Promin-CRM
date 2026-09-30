from django import template

register = template.Library()

@register.filter
def is_teacher(user):
    return getattr(user, "role", None) == "teacher"

@register.filter
def is_editor(user):
    return user.groups.filter(name="Editor").exists()