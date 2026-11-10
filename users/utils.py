def is_editor(user):
    return user.groups.filter(name="Editor").exists()

def is_root_editor(user):
    return user.groups.filter(name="Root Editor").exists()

def can_review_post(user, post):
    # Post author or Root Editor can approve/reject attendance requests
    return post.author_id == user.id or is_root_editor(user)
