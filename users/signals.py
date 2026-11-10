from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Attachment


# Django does not remove the stored file when a model row is deleted.
# Without this, every withdrawn request or replaced certificate would leave
# an orphan file in Supabase storage and slowly eat the storage limit.
@receiver(post_delete, sender=Attachment)
def delete_attachment_file(sender, instance, **kwargs):
    if not instance.file:
        return
    storage, name = instance.file.storage, instance.file.name
    # Delete only after the DB transaction commits: if it is rolled back,
    # the row stays and so must its file. robust=True logs a storage error
    # instead of breaking the user's request.
    transaction.on_commit(lambda: storage.delete(name), robust=True)
