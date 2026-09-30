from .utils import is_editor
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .forms import PostForm
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .models import User, Post

# Create your views here.
def index(request):
    return HttpResponse("Hello, world. You're at the home index.")

@login_required
def home(request):
    return render(request, "users/home.html")

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

@login_required
def post_detail(request, pk):
    post = get_object_or_404(Post, pk=pk)
    context = {"post" : post}
    return render(request, "users/post_detail.html", context)

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
        form = PostForm
    return render(request, 'users/post_edit.html', {'form': form, 'is_edit': False})

@login_required
def post_edit(request, pk):
    if not is_editor(request.user):
        return redirect('users:posts')
    post = get_object_or_404(Post, pk=pk)
    if request.method == "POST":
        form = PostForm(request.POST, instance=post)
        if form.is_valid():
            post = form.save(commit=False)
            post.save()
            return redirect('users:post_detail', pk=post.pk)
    else:    
        form = PostForm
    return render(request, 'users/post_edit.html', {'form': form, 'is_edit': True})

#def user_login(request):
#    if request.method == "POST":
#        login_value = request.POST.get('login', '')
#        password_value = request.POST.get("password", '')
#        print(login_value)
#        return HttpResponse(f"Received: {login_value}")

#    return HttpResponse("Nothing happened")