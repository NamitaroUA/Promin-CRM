from django.shortcuts import render
from django.http import HttpResponse

# Create your views here.
def index(request):
    return HttpResponse("Hello, world. You're at the home index.")

def login(request):
    return render(request, "users/login.html")

def user_login(request):
    if request.method == "POST":
        login_value = request.POST.get('login', '')
        password_value = request.POST.get("password", '')
        print(login_value)
        return HttpResponse(f"Received: {login_value}")

    return HttpResponse("Nothing happened")