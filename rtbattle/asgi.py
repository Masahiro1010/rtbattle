# rtbattle/asgi.py
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rtbattle.settings")  # ✅ 最初に設定

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from channels.auth import AuthMiddlewareStack

django_asgi_app = get_asgi_application()

# settings が効いた後で arena のroutingを import
from arena import routing as arena_routing

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(arena_routing.websocket_urlpatterns)
    ),
})
