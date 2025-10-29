from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/arena/(?P<room_code>\d{6})/$", consumers.BattleConsumer.as_asgi()),
]
