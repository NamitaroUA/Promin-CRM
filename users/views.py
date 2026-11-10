from .utils import is_editor, is_root_editor, can_review_post
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .forms import PostForm, AttendanceForm
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import User, Post, PostAttendance
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.db.models import Case, Count, IntegerField, Prefetch, Q, Value, When
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

# Create your views here.

@login_required
def home(request):
    context = {}
    root = is_root_editor(request.user)
    if root or is_editor(request.user):
        pending = PostAttendance.objects.filter(status="pending")
        if not root:
            pending = pending.filter(post__author=request.user)
        context["pending_reviews_count"] = pending.count()
    return render(request, "users/home.html", context)

@login_required
def profile(request, pk):
    userObj = get_object_or_404(User, pk=pk)
    context = {'userObj': userObj}

    return render(request, "users/profile.html", context)

@login_required
def posts(request):
    posts_list = Post.objects.all()
    filtered = posts_list.order_by('-created_at')

    context = {'posts_list': filtered}

    return render(request, "users/posts.html", context)

def _post_detail_context(request, post, form=None):
    """Context for post_detail.html (also used to re-render it with a bound form)."""
    can_review = can_review_post(request.user, post)
    my_attendance = (
        PostAttendance.objects.filter(user=request.user, post=post)
        .prefetch_related("attachments")
        .first()
    )
    if post.author_id == request.user.id:
        attendance_form = None
    elif my_attendance is None:
        attendance_form = form or AttendanceForm()
    elif my_attendance.status == "rejected":
        attendance_form = form or AttendanceForm(instance=my_attendance)
    else:
        attendance_form = None

    attendances = None
    if can_review:
        # Pending first, then rejected, then approved; oldest first within a group
        attendances = (
            post.attendances.select_related("user")
            .prefetch_related("attachments")
            .annotate(
                status_order=Case(
                    When(status="pending", then=Value(0)),
                    When(status="rejected", then=Value(1)),
                    default=Value(2),
                    output_field=IntegerField(),
                )
            )
            .order_by("status_order", "created_at")
        )

    return {
        "post": post,
        "can_review": can_review,
        "my_attendance": my_attendance,
        "attendance_form": attendance_form,
        "attendances": attendances,
    }

@login_required
def post_detail(request, pk):
    post = get_object_or_404(Post, pk=pk)
    return render(request, "users/post_detail.html", _post_detail_context(request, post))

@login_required
def post_new(request):
    if not is_editor(request.user):
        return redirect('users:posts')
    if request.method == "POST":
        form = PostForm(request.POST)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.save()
            return redirect('users:posts')
    else:    
        form = PostForm()
    return render(request, 'users/post_edit.html', {'form': form, 'is_edit': False})

@login_required
def post_edit(request, pk):
    if not is_editor(request.user):
        return redirect('users:posts')
    post = get_object_or_404(Post, pk=pk)
    # Only the author of the post can edit it
    if post.author_id != request.user.id:
        return redirect('users:post_detail', pk=post.pk)
    if request.method == "POST":
        form = PostForm(request.POST, instance=post)
        if form.is_valid():
            post = form.save(commit=False)
            post.save()
            return redirect('users:post_detail', pk=post.pk)
    else:    
        form = PostForm(instance=post)
    return render(request, 'users/post_edit.html', {'form': form, 'is_edit': True})


@login_required
@require_POST
def attendance_submit(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if post.author_id == request.user.id:
        messages.error(request, "Ви не можете подати заявку на власний пост.")
        return redirect("users:post_detail", pk=post.pk)
    existing = PostAttendance.objects.filter(user=request.user, post=post).first()
    if existing is not None and existing.status != "rejected":
        messages.error(request, "Ви вже подали заявку на цей пост.")
        return redirect("users:post_detail", pk=post.pk)

    form = AttendanceForm(request.POST, request.FILES, instance=existing)
    if form.is_valid():
        if existing is None:
            form.instance.user = request.user
            form.instance.post = post
        # Resubmission after rejection reuses the same row
        form.instance.status = "pending"
        form.instance.review_comment = ""
        try:
            form.save()
        except IntegrityError:
            # Double submit race: the unique constraint caught the duplicate
            messages.error(request, "Ви вже подали заявку на цей пост.")
            return redirect("users:post_detail", pk=post.pk)
        messages.success(request, "Заявку надіслано. Очікуйте на підтвердження.")
        return redirect("users:post_detail", pk=post.pk)

    context = _post_detail_context(request, post, form=form)
    return render(request, "users/post_detail.html", context, status=400)


@login_required
def attendance_edit(request, pk):
    # Other users get 404 so the existence of a request is not revealed
    attendance = get_object_or_404(
        PostAttendance.objects.select_related("post").prefetch_related("attachments"),
        pk=pk,
        user=request.user,
    )
    if attendance.status != "pending":
        messages.error(request, "Змінити можна лише заявку, що очікує розгляду.")
        return redirect("users:post_detail", pk=attendance.post_id)

    if request.method == "POST":
        form = AttendanceForm(request.POST, request.FILES, instance=attendance)
        if form.is_valid():
            form.save()
            messages.success(request, "Заявку оновлено.")
            return redirect("users:post_detail", pk=attendance.post_id)
        status = 400
    else:
        form = AttendanceForm(instance=attendance)
        status = 200
    context = {"form": form, "attendance": attendance}
    return render(request, "users/attendance_edit.html", context, status=status)


@login_required
@require_POST
def attendance_withdraw(request, pk):
    attendance = get_object_or_404(PostAttendance, pk=pk, user=request.user)
    post_pk = attendance.post_id
    if attendance.status == "approved":
        messages.error(request, "Підтверджену заявку відкликати не можна.")
        return redirect("users:post_detail", pk=post_pk)
    # Cascade removes Attachment rows; the post_delete signal removes the files
    attendance.delete()
    messages.success(request, "Заявку відкликано.")
    return redirect("users:post_detail", pk=post_pk)


def _load_reviewable_attendance(request, pk):
    attendance = get_object_or_404(PostAttendance.objects.select_related("post", "user"), pk=pk)
    if not can_review_post(request.user, attendance.post):
        raise PermissionDenied
    # Nobody may decide on their own request
    if attendance.user_id == request.user.id:
        raise PermissionDenied
    return attendance


def _review_redirect(request, attendance):
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("users:post_detail", pk=attendance.post_id)


@login_required
@require_POST
def attendance_approve(request, pk):
    attendance = _load_reviewable_attendance(request, pk)
    attendance.status = "approved"
    attendance.review_comment = ""
    attendance.save(update_fields=["status", "review_comment", "last_edit"])
    messages.success(
        request, f"Заявку {attendance.user.get_full_name()} підтверджено."
    )
    return _review_redirect(request, attendance)


@login_required
@require_POST
def attendance_reject(request, pk):
    attendance = _load_reviewable_attendance(request, pk)
    comment = request.POST.get("review_comment", "").strip()
    if len(comment) > 500:
        messages.error(request, "Причина відхилення має містити не більше 500 символів.")
        return _review_redirect(request, attendance)
    attendance.status = "rejected"
    attendance.review_comment = comment
    attendance.save(update_fields=["status", "review_comment", "last_edit"])
    messages.success(
        request, f"Заявку {attendance.user.get_full_name()} відхилено."
    )
    return _review_redirect(request, attendance)


@login_required
@require_GET
def reviews(request):
    root = is_root_editor(request.user)
    base = Post.objects.all() if root else Post.objects.filter(author=request.user)
    posts_qs = (
        base.select_related("author")
        .annotate(pending_count=Count("attendances", filter=Q(attendances__status="pending")))
        .prefetch_related(
            Prefetch(
                "attendances",
                queryset=PostAttendance.objects.filter(status="pending")
                .select_related("user")
                .prefetch_related("attachments")
                .order_by("created_at"),
                to_attr="pending_attendances",
            )
        )
        .order_by("-pending_count", "-created_at")
    )
    if root:
        # Listing every post of the college would be noise
        posts_qs = posts_qs.filter(pending_count__gt=0)
    posts_list = list(posts_qs)
    return render(request, "users/reviews.html", {
        "posts": posts_list,
        "is_root": root,
        "total_pending": sum(p.pending_count for p in posts_list),
    })
