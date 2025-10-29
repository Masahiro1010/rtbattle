from django.shortcuts import render, redirect
from django.utils.crypto import get_random_string
from .models import Room

def index(request):
    if request.method == "POST":
        if "create" in request.POST:
            code = get_random_string(6, allowed_chars="0123456789")
            Room.objects.create(code=code)
            return redirect("room", room_code=code)
        code = request.POST.get("code", "").strip()
        if len(code) == 6 and Room.objects.filter(code=code).exists():
            return redirect("room", room_code=code)
    return render(request, "arena/index.html")

def room(request, room_code):
    return render(request, "arena/room.html", {"room_code": room_code})

# Create your views here.
