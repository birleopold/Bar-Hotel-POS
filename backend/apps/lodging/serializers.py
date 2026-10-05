from decimal import Decimal

from django.db import transaction

from rest_framework import serializers

from apps.accounts.models import MembershipRole
from apps.tenants.models import Site

from .models import Folio, FolioLine, FolioPayment, FolioPaymentMethod, FolioStatus, Reservation, ReservationStatus, Room, RoomRateWindow, RoomType
from .services import cancel_reservation, check_in_reservation, check_out_reservation, folio_totals, validate_room_available_for_reservation


class RoomTypeSerializer(serializers.ModelSerializer):
    site = serializers.PrimaryKeyRelatedField(queryset=Site.objects.none())
    site_id = serializers.UUIDField(source="site.id", read_only=True)
    site_name = serializers.CharField(source="site.name", read_only=True)

    class Meta:
        model = RoomType
        fields = [
            "id",
            "site",
            "site_id",
            "site_name",
            "name",
            "description",
            "max_occupancy",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("id", "site_id", "site_name", "created_at", "updated_at")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        tenant = getattr(request, "tenant", None) if request else None
        if tenant is not None:
            self.fields["site"].queryset = Site.objects.filter(tenant=tenant)

    def validate_site(self, value: Site) -> Site:
        request = self.context["request"]
        if value.tenant_id != request.tenant.id:
            raise serializers.ValidationError("Site must belong to the current tenant.")
        membership = request.tenant_membership
        if (membership.role not in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN) or membership.sites.exists()) and value.id not in membership.sites.values_list("pk", flat=True):
            raise serializers.ValidationError("You cannot create or update room types for this site.")
        if not _tenant_has_lodging(request.tenant):
            raise serializers.ValidationError("Lodging is not enabled for this workspace.")
        return value

    def create(self, validated_data):
        validated_data["tenant"] = self.context["request"].tenant
        return super().create(validated_data)


class RoomSerializer(serializers.ModelSerializer):
    room_type = serializers.PrimaryKeyRelatedField(queryset=RoomType.objects.none())
    room_type_id = serializers.UUIDField(source="room_type.id", read_only=True)
    room_type_name = serializers.CharField(source="room_type.name", read_only=True)

    class Meta:
        model = Room
        fields = [
            "id",
            "room_type",
            "room_type_id",
            "room_type_name",
            "name",
            "status",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("id", "room_type_id", "room_type_name", "created_at", "updated_at")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        tenant = getattr(request, "tenant", None) if request else None
        if tenant is not None:
            self.fields["room_type"].queryset = RoomType.objects.filter(tenant=tenant)

    def validate_room_type(self, value: RoomType) -> RoomType:
        request = self.context["request"]
        if value.tenant_id != request.tenant.id:
            raise serializers.ValidationError("Room type must belong to the current tenant.")
        membership = request.tenant_membership
        if (membership.role not in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN) or membership.sites.exists()) and value.site_id not in membership.sites.values_list("pk", flat=True):
            raise serializers.ValidationError("You cannot create or update rooms for this site.")
        if not _tenant_has_lodging(request.tenant):
            raise serializers.ValidationError("Lodging is not enabled for this workspace.")
        return value


class ReservationSerializer(serializers.ModelSerializer):
    site = serializers.PrimaryKeyRelatedField(queryset=Site.objects.none())
    site_id = serializers.UUIDField(source="site.id", read_only=True)
    site_name = serializers.CharField(source="site.name", read_only=True)
    room = serializers.PrimaryKeyRelatedField(
        queryset=Room.objects.none(),
        allow_null=True,
        required=False,
    )
    room_id = serializers.UUIDField(source="room.id", read_only=True, allow_null=True)
    room_label = serializers.CharField(source="room.name", read_only=True, allow_null=True)

    class Meta:
        model = Reservation
        fields = [
            "id",
            "site",
            "site_id",
            "site_name",
            "guest_name",
            "guest_email",
            "guest_phone",
            "check_in",
            "check_out",
            "status",
            "room",
            "room_id",
            "room_label",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = (
            "id",
            "site_id",
            "site_name",
            "room_id",
            "room_label",
            "status",
            "created_at",
            "updated_at",
        )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        tenant = getattr(request, "tenant", None) if request else None
        if tenant is not None:
            self.fields["site"].queryset = Site.objects.filter(tenant=tenant)
            self.fields["room"].queryset = Room.objects.filter(room_type__tenant=tenant)

    def validate(self, attrs: dict) -> dict:
        if "status" in self.initial_data:
            requested_status = self.initial_data.get("status")
            if self.instance is not None and requested_status == self.instance.status:
                attrs.pop("status", None)
            else:
                raise serializers.ValidationError({"status": "Use the check-in, check-out, or cancel action to change reservation status."})
        check_in = attrs.get("check_in") or (self.instance.check_in if self.instance else None)
        check_out = attrs.get("check_out") or (self.instance.check_out if self.instance else None)
        if check_in and check_out and check_out <= check_in:
            raise serializers.ValidationError({"check_out": "Must be after check-in."})

        site = attrs.get("site")
        if site is None and self.instance:
            site = self.instance.site

        room = serializers.empty
        if "room" in attrs:
            room = attrs["room"]
        elif self.instance is not None:
            room = self.instance.room

        if room is not serializers.empty and room is not None and site is not None:
            if room.room_type.site_id != site.id:
                raise serializers.ValidationError(
                    {"room": "Room must belong to the same site as the reservation."}
                )
            if check_in and check_out:
                req = self.context.get("request")
                tenant = getattr(req, "tenant", None) if req else None
                tmp = self.instance or Reservation()
                tmp.tenant = tenant
                tmp.site = site
                tmp.room = room
                tmp.check_in = check_in
                tmp.check_out = check_out
                try:
                    validate_room_available_for_reservation(reservation=tmp, room=room)
                except Exception as exc:
                    # Normalize DRF ValidationError / Django ValidationError into serializer error.
                    raise serializers.ValidationError(getattr(exc, "detail", None) or str(exc))
        return attrs

    def validate_site(self, value: Site) -> Site:
        request = self.context["request"]
        if value.tenant_id != request.tenant.id:
            raise serializers.ValidationError("Site must belong to the current tenant.")
        membership = request.tenant_membership
        if (membership.role not in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN) or membership.sites.exists()) and value.id not in membership.sites.values_list("pk", flat=True):
            raise serializers.ValidationError("You cannot create or update reservations for this site.")
        if not _tenant_has_lodging(request.tenant):
            raise serializers.ValidationError("Lodging is not enabled for this workspace.")
        return value

    def validate_room(self, value: Room | None) -> Room | None:
        if value is None:
            return value
        if value.room_type.tenant_id != self.context["request"].tenant.id:
            raise serializers.ValidationError("Room must belong to the current tenant.")
        membership = self.context["request"].tenant_membership
        if (membership.role not in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN) or membership.sites.exists()) and value.room_type.site_id not in membership.sites.values_list("pk", flat=True):
            raise serializers.ValidationError("You cannot use rooms at this site.")
        return value

    def create(self, validated_data):
        validated_data["tenant"] = self.context["request"].tenant
        with transaction.atomic():
            room = validated_data.get("room")
            if room is not None:
                Room.objects.select_for_update().get(pk=room.pk)
                candidate = Reservation(**validated_data)
                validate_room_available_for_reservation(reservation=candidate, room=room)
            return super().create(validated_data)

    def update(self, instance, validated_data):
        with transaction.atomic():
            room = validated_data.get("room", instance.room)
            if room is not None:
                Room.objects.select_for_update().get(pk=room.pk)
                candidate = Reservation(
                    id=instance.id,
                    tenant=instance.tenant,
                    site=validated_data.get("site", instance.site),
                    room=room,
                    check_in=validated_data.get("check_in", instance.check_in),
                    check_out=validated_data.get("check_out", instance.check_out),
                )
                validate_room_available_for_reservation(reservation=candidate, room=room)
            return super().update(instance, validated_data)


class FolioLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = FolioLine
        fields = [
            "id",
            "description",
            "amount",
            "tax_amount",
            "source_order",
            "created_at",
        ]
        read_only_fields = fields


class FolioPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = FolioPayment
        fields = ["id", "amount", "method", "reference", "created_at"]
        read_only_fields = fields


class FolioSerializer(serializers.ModelSerializer):
    lines = FolioLineSerializer(many=True, read_only=True)
    payments = FolioPaymentSerializer(many=True, read_only=True)
    total_charges = serializers.SerializerMethodField()
    total_paid = serializers.SerializerMethodField()
    balance_due = serializers.SerializerMethodField()
    site_id = serializers.UUIDField(source="site.id", read_only=True)
    site_name = serializers.CharField(source="site.name", read_only=True)

    class Meta:
        model = Folio
        fields = [
            "id",
            "tenant",
            "site",
            "site_id",
            "site_name",
            "reservation",
            "guest_name",
            "status",
            "currency",
            "notes",
            "lines",
            "payments",
            "total_charges",
            "total_paid",
            "balance_due",
            "created_at",
            "updated_at",
        ]
        read_only_fields = (
            "id",
            "tenant",
            "site",
            "site_id",
            "site_name",
            "reservation",
            "guest_name",
            "currency",
            "notes",
            "status",
            "lines",
            "created_at",
            "updated_at",
        )

    def get_total_charges(self, obj: Folio) -> str:
        return str(folio_totals(obj)[0].quantize(Decimal("0.01")))

    def get_total_paid(self, obj: Folio) -> str:
        return str(folio_totals(obj)[1].quantize(Decimal("0.01")))

    def get_balance_due(self, obj: Folio) -> str:
        return str(folio_totals(obj)[2].quantize(Decimal("0.01")))


class FolioCreateSerializer(serializers.ModelSerializer):
    site = serializers.PrimaryKeyRelatedField(queryset=Site.objects.none())
    reservation = serializers.PrimaryKeyRelatedField(
        queryset=Reservation.objects.none(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Folio
        fields = ["site", "reservation", "guest_name", "currency", "notes"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        tenant = getattr(request, "tenant", None) if request else None
        if tenant is not None:
            self.fields["site"].queryset = Site.objects.filter(tenant=tenant)
            self.fields["reservation"].queryset = Reservation.objects.filter(tenant=tenant)

    def validate_site(self, value: Site) -> Site:
        req = self.context["request"]
        if value.tenant_id != req.tenant.id:
            raise serializers.ValidationError("Site must belong to the current tenant.")
        m = req.tenant_membership
        if (m.role not in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN) or m.sites.exists()) and value.id not in m.sites.values_list("pk", flat=True):
            raise serializers.ValidationError("You cannot create a folio for this site.")
        if not _tenant_has_lodging(req.tenant):
            raise serializers.ValidationError("Lodging is not enabled for this workspace.")
        return value

    def validate(self, attrs: dict) -> dict:
        res = attrs.get("reservation")
        site = attrs.get("site")
        if res is not None and site is not None and res.site_id != site.id:
            raise serializers.ValidationError(
                {"reservation": "Reservation must belong to the selected site."}
            )
        return attrs

    def create(self, validated_data):
        validated_data["tenant"] = self.context["request"].tenant
        tenant = self.context["request"].tenant
        try:
            default_currency = tenant.settings.default_currency
        except Exception:
            default_currency = "USD"
        validated_data.setdefault("currency", default_currency)
        return super().create(validated_data)


class FolioStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Folio
        fields = ["status"]

    def validate_status(self, value: str) -> str:
        inst = self.instance
        if inst is None:
            return value
        if value == inst.status:
            return value
        if value == FolioStatus.CLOSED and inst.status == FolioStatus.OPEN:
            return value
        raise serializers.ValidationError("Invalid status transition.")


class FolioManualLineSerializer(serializers.Serializer):
    description = serializers.CharField(max_length=512)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    tax_amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        required=False,
    )


class FolioPaymentCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    method = serializers.ChoiceField(choices=FolioPaymentMethod.choices)
    reference = serializers.CharField(max_length=128, allow_blank=True, required=False, default="")
    idempotency_key = serializers.CharField(max_length=128)


class RoomRateWindowSerializer(serializers.ModelSerializer):
    room_type = serializers.PrimaryKeyRelatedField(queryset=RoomType.objects.none())

    class Meta:
        model = RoomRateWindow
        fields = [
            "id",
            "room_type",
            "label",
            "valid_from",
            "valid_to",
            "nightly_amount",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("id", "created_at", "updated_at")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        tenant = getattr(request, "tenant", None) if request else None
        if tenant is not None:
            self.fields["room_type"].queryset = RoomType.objects.filter(tenant=tenant)

    def validate_room_type(self, value: RoomType) -> RoomType:
        request = self.context["request"]
        if value.tenant_id != request.tenant.id:
            raise serializers.ValidationError("Room type must belong to the current tenant.")
        membership = request.tenant_membership
        if (membership.role not in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN) or membership.sites.exists()) and value.site_id not in membership.sites.values_list("pk", flat=True):
            raise serializers.ValidationError("You cannot manage rates for this site.")
        if not _tenant_has_lodging(request.tenant):
            raise serializers.ValidationError("Lodging is not enabled for this workspace.")
        return value


def _tenant_has_lodging(tenant) -> bool:
    from apps.staff.services.modules import get_tenant_staff_modules
    from apps.tenants.business_lines import normalize_business_lines

    try:
        return "lodging" in normalize_business_lines(tenant.settings.business_lines) and "lodging" in get_tenant_staff_modules(tenant)
    except Exception:
        return False


class ReservationFolioChargeSerializer(serializers.Serializer):
    folio_id = serializers.UUIDField()
    description = serializers.CharField(max_length=512)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    tax_amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        required=False,
    )
