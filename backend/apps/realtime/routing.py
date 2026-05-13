from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path(
        "ws/kds/<uuid:tenant_id>/<uuid:outlet_id>/",
        consumers.KdsKitchenConsumer.as_asgi(),
        name="ws-kds-kitchen",
    ),
]
