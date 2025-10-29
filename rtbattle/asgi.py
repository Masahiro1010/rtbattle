# rtbattle/asgi.py
import os
import django

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rtbattle.settings")
django.setup()  # ← これが routing を import するより先！

from arena import routing as arena_routing  # ← ここで初めて import する

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(arena_routing.websocket_urlpatterns)
    ),
})
