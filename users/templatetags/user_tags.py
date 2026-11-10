from django import template
from users.utils import is_editor, is_root_editor, can_review_post

register = template.Library()

@register.filter
def is_teacher(user):
    return getattr(user, "role", None) == "teacher"

register.filter("is_editor", is_editor)
register.filter("is_root_editor", is_root_editor)

# Usage in templates: {% if user|can_review:post %}
register.filter("can_review", can_review_post)
