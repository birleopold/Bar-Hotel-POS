import uuid

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

from apps.common.models import TimeStampedModel


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError("Email must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField("email address", unique=True)
    phone = models.CharField(max_length=32, blank=True)
    is_platform_staff = models.BooleanField(
        default=False,
        help_text="Internal operator; not a tenant user.",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        ordering = ["email"]

    def __str__(self) -> str:
        return self.email


class MembershipRole(models.TextChoices):
    OWNER = "owner", "Owner"
    TENANT_ADMIN = "tenant_admin", "Tenant admin"
    SITE_MANAGER = "site_manager", "Site manager"
    OUTLET_MANAGER = "outlet_manager", "Outlet manager"
    FRONT_DESK = "front_desk", "Front desk"
    SERVER = "server", "Server / floor"
    BARTENDER = "bartender", "Bartender"
    KITCHEN = "kitchen", "Kitchen"
    STOREKEEPER = "storekeeper", "Storekeeper"
    ACCOUNTANT = "accountant", "Accountant (read-only)"


class Membership(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=32, choices=MembershipRole.choices)
    is_active = models.BooleanField(default=True)
    staff_pin_hash = models.CharField(max_length=255, blank=True, editable=False)
    staff_pin_failures = models.PositiveSmallIntegerField(default=0, editable=False)
    staff_pin_locked_until = models.DateTimeField(null=True, blank=True, editable=False)
    sites = models.ManyToManyField(
        "tenants.Site",
        blank=True,
        related_name="memberships",
        help_text="Empty = access to all sites for this tenant.",
    )
    outlets = models.ManyToManyField(
        "tenants.Outlet",
        blank=True,
        related_name="memberships",
        help_text="Empty = access to all outlets under allowed sites.",
    )

    class Meta:
        ordering = ["tenant", "user"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "tenant"],
                name="uniq_membership_user_tenant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user.email} @ {self.tenant.slug} ({self.role})"


class UserInvite(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="user_invites",
    )
    email = models.EmailField()
    role = models.CharField(max_length=32, choices=MembershipRole.choices)
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    invited_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invites_sent",
    )
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Invite {self.email} → {self.tenant.slug}"
