def is_editor(user):
    return user.groups.filter(name="Editor").exists()