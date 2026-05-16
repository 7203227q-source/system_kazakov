from django.urls import re_path

from core.consumers import WhiteboardConsumer

websocket_urlpatterns = [
    re_path(r"^ws/board/(?P<session_id>\d+)/$", WhiteboardConsumer.as_asgi()),
]

