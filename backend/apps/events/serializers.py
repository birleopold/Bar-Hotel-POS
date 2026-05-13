from rest_framework import serializers

from apps.tenants.models import Site

from .models import EventBooking, EventBookingStatus, EventSpace


class EventSpaceSerializer(serializers.ModelSerializer):
    site = serializers.PrimaryKeyRelatedField(queryset=Site.objects.none())

    class Meta:
        model = EventSpace
        fields = [
            "id",
            "tenant",
            "site",
            "name",
            "capacity",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("id", "tenant", "created_at", "updated_at")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        tenant = getattr(request, "tenant", None) if request else None
        if tenant is not None:
            self.fields["site"].queryset = Site.objects.filter(tenant=tenant)

    def validate_site(self, value):
        request = self.context["request"]
        if value.tenant_id != request.tenant.id:
            raise serializers.ValidationError("Site must belong to the current tenant.")
        membership = request.tenant_membership
        if membership.sites.exists() and value.id not in membership.sites.values_list("pk", flat=True):
            raise serializers.ValidationError("You cannot create or update spaces for this site.")
        return value

    def create(self, validated_data):
        validated_data["tenant"] = self.context["request"].tenant
        return super().create(validated_data)


class EventBookingSerializer(serializers.ModelSerializer):
    space = serializers.PrimaryKeyRelatedField(queryset=EventSpace.objects.none())

    class Meta:
        model = EventBooking
        fields = [
            "id",
            "tenant",
            "space",
            "title",
            "customer_name",
            "customer_email",
            "customer_phone",
            "start_at",
            "end_at",
            "status",
            "headcount",
            "notes",
            "deposit_amount",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("id", "tenant", "created_at", "updated_at")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        tenant = getattr(request, "tenant", None) if request else None
        if tenant is not None:
            self.fields["space"].queryset = EventSpace.objects.filter(tenant=tenant)

    def validate_space(self, value: EventSpace):
        request = self.context["request"]
        if value.tenant_id != request.tenant.id:
            raise serializers.ValidationError("Invalid event space.")
        membership = request.tenant_membership
        if membership.sites.exists() and value.site_id not in membership.sites.values_list("pk", flat=True):
            raise serializers.ValidationError("You cannot create or update bookings for this site.")
        return value

    def validate(self, attrs):
        start = attrs.get("start_at") or getattr(self.instance, "start_at", None)
        end = attrs.get("end_at") or getattr(self.instance, "end_at", None)
        if start and end and end <= start:
            raise serializers.ValidationError({"end_at": "Must be after start_at."})
        space = attrs.get("space") or getattr(self.instance, "space", None)
        if space and start and end:
            qs = EventBooking.objects.filter(
                space=space,
                tenant_id=space.tenant_id,
            ).exclude(status=EventBookingStatus.CANCELLED)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.filter(start_at__lt=end, end_at__gt=start).exists():
                raise serializers.ValidationError(
                    {"start_at": "This space already has a booking that overlaps these times."}
                )
        return attrs

    def create(self, validated_data):
        validated_data["tenant"] = self.context["request"].tenant
        return super().create(validated_data)
