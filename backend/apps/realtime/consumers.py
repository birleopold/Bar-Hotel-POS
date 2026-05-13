import json
import logging
import uuid

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


def _kds_group_name(tenant_id, outlet_id) -> str:
    return f"kds_{tenant_id}_{outlet_id}"


@database_sync_to_async
def _staff_kds_allowed(user, tenant_id: uuid.UUID, outlet_id: uuid.UUID) -> bool:
    from apps.accounts.models import Membership
    from apps.staff.services import staff_outlet_allowed_for_membership

    if not user.is_authenticated:
        return False
    membership = (
        Membership.objects.filter(
            user=user,
            tenant_id=tenant_id,
            is_active=True,
        )
        .select_related("tenant")
        .first()
    )
    if membership is None:
        return False
    return staff_outlet_allowed_for_membership(membership, outlet_id)


class KdsKitchenConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.tenant_id: uuid.UUID = self.scope["url_route"]["kwargs"]["tenant_id"]
        self.outlet_id: uuid.UUID = self.scope["url_route"]["kwargs"]["outlet_id"]
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            logger.warning(
                "realtime.kds.connect_denied",
                extra={
                    "reason": "unauthenticated",
                    "tenant_id": str(self.tenant_id),
                    "outlet_id": str(self.outlet_id),
                },
            )
            await self.close(code=4401)
            return
        if not await _staff_kds_allowed(user, self.tenant_id, self.outlet_id):
            logger.warning(
                "realtime.kds.connect_denied",
                extra={
                    "reason": "forbidden",
                    "tenant_id": str(self.tenant_id),
                    "outlet_id": str(self.outlet_id),
                    "user_id": str(user.id),
                },
            )
            await self.close(code=4403)
            return

        self.group = _kds_group_name(self.tenant_id, self.outlet_id)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        logger.info(
            "realtime.kds.connected",
            extra={
                "tenant_id": str(self.tenant_id),
                "outlet_id": str(self.outlet_id),
                "user_id": str(user.id),
            },
        )

    async def disconnect(self, close_code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)
        user = self.scope.get("user")
        logger.info(
            "realtime.kds.disconnected",
            extra={
                "tenant_id": str(getattr(self, "tenant_id", "")),
                "outlet_id": str(getattr(self, "outlet_id", "")),
                "user_id": str(getattr(user, "id", "")) if user else "",
                "close_code": str(close_code),
            },
        )

    async def kds_notify(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": event.get("event", "queue_changed"),
                }
            )
        )
