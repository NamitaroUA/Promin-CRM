from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .models import User

# Create your views here.
def index(request):
    return HttpResponse("Hello, world. You're at the home index.")

@login_required
def home(request):
    return render(request, "users/home.html")

@login_required
def profile(request, user_id):
    userObj = User.objects.get(id=user_id)

    context = {'userObj': userObj}

    return render(request, "users/profile.html", context)

#def user_login(request):
#    if request.method == "POST":
#        login_value = request.POST.get('login', '')
#        password_value = request.POST.get("password", '')
#        print(login_value)
#        return HttpResponse(f"Received: {login_value}")

#    return HttpResponse("Nothing happened")