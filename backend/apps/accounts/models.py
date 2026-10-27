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
    CLEANER = "cleaner", "Housekeeping"


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
        help_text="Workers must be assigned one or more sites. Empty means no site access.",
    )
    outlets = models.ManyToManyField(
        "tenants.Outlet",
        blank=True,
        related_name="memberships",
        help_text="When outlets are assigned, access is limited to those outlets. Empty means all permitted outlets under assigned sites.",
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


class RoleTemplate(TimeStampedModel):
    """Tenant-scoped reusable staff role and location profile.

    Templates never create new permission primitives. The base role must remain
    one of the tenant's permitted built-in roles; optional site/outlet defaults
    only narrow where that role is usable.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="role_templates",
    )
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=255, blank=True)
    base_role = models.CharField(max_length=32, choices=MembershipRole.choices)
    sites = models.ManyToManyField(
        "tenants.Site",
        blank=True,
        related_name="role_templates",
    )
    outlets = models.ManyToManyField(
        "tenants.Outlet",
        blank=True,
        related_name="role_templates",
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="role_templates_created",
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "name"],
                name="uniq_role_template_name_per_tenant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_base_role_display()})"


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
    sites = models.ManyToManyField("tenants.Site", blank=True, related_name="user_invites")
    outlets = models.ManyToManyField("tenants.Outlet", blank=True, related_name="user_invites")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Invite {self.email} → {self.tenant.slug}"


class PasswordRecoveryRequest(models.Model):
    """Platform-reviewed recovery; never store a plaintext reset token."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="recovery_requests")
    requested_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=16, default="pending", choices=[
        ("pending", "Pending review"), ("sent", "Approved and emailed"),
        ("used", "Used"), ("denied", "Denied"),
    ])
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="approved_recoveries")
    approved_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    token_digest = models.CharField(max_length=64, blank=True, editable=False)

    class Meta:
        ordering = ["-requested_at"]
        indexes = [models.Index(fields=["user", "status", "requested_at"], name="accounts_pr_user_id_85d14d_idx")]

