from django.shortcuts import render

# Create your views here.

def index(request):
    return render(request, "frontpage/index.html")

def about(request):
    return render(request, "frontpage/about.html")

def base(request):
    return render(request, "frontpage/base.html")