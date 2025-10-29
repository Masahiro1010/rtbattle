from django.contrib import admin
from django.urls import path
from arena import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.index, name="index"),
    path("room/<str:room_code>/", views.room, name="room"),
]