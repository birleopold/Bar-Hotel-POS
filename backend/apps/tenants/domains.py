from __future__ import annotations

import hashlib
import ipaddress
import secrets

from django.core.cache import cache
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.text import slugify

from .models import Tenant, TenantDomain


def normalize_hostname(value: str) -> str:
    value = (value or "").strip().rstrip(".").lower()
    if not value or any(ch in value for ch in ":/@\\"):
        raise ValidationError("Enter a hostname without a scheme, port, path, or credentials.")
    try:
        hostname = value.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValidationError("Enter a valid internationalized hostname.") from exc
    labels = hostname.split(".")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ValidationError("Enter a public DNS hostname, not an IP address.")
    if len(labels) < 2 or len(hostname) > 253 or any(
        not label
        or len(label) > 63
        or not all(ch.isalnum() or ch == "-" for ch in label)
        or label.startswith("-")
        or label.endswith("-")
        for label in labels
    ):
        raise ValidationError("Enter a valid DNS hostname.")
    return hostname


def platform_domain_suffix() -> str:
    value = (getattr(settings, "TENANT_PLATFORM_DOMAIN", "") or "").strip()
    return normalize_hostname(value) if value else ""


def create_platform_domain(tenant: Tenant) -> TenantDomain | None:
    suffix = platform_domain_suffix()
    prefix = slugify(tenant.slug).strip("-")
    if not suffix or not prefix:
        return None
    if len(prefix) > 63:
        digest = hashlib.sha256(tenant.slug.encode("utf-8")).hexdigest()[:8]
        prefix = f"{prefix[:54].rstrip('-')}-{digest}"
    hostname = normalize_hostname(f"{prefix}.{suffix}")
    domain, _ = TenantDomain.objects.get_or_create(
        hostname=hostname,
        defaults={"tenant": tenant, "kind": TenantDomain.Kind.PLATFORM,
                  "status": TenantDomain.Status.ACTIVE,
                  "is_primary": not TenantDomain.objects.filter(tenant=tenant, is_primary=True).exists(),
                  "tls_status": "managed"},
    )
    if domain.tenant_id != tenant.pk:
        raise ValidationError("That workspace subdomain is already assigned to another workspace.")
    if domain.kind != TenantDomain.Kind.PLATFORM:
        raise ValidationError("That hostname is already registered as a custom domain.")
    changed = False
    if domain.status != TenantDomain.Status.ACTIVE:
        domain.status = TenantDomain.Status.ACTIVE
        domain.tls_status = "managed"
        changed = True
    if not domain.is_primary and not TenantDomain.objects.filter(
        tenant=tenant, is_primary=True, status=TenantDomain.Status.ACTIVE
    ).exclude(pk=domain.pk).exists():
        domain.is_primary = True
        changed = True
    if changed:
        domain.save(update_fields=["status", "tls_status", "is_primary", "updated_at"])
    cache.delete(f"tenant-domain:{hostname}")
    return domain


def begin_custom_domain_verification(tenant: Tenant, hostname: str) -> TenantDomain:
    hostname = normalize_hostname(hostname)
    central_hosts = {
        normalize_hostname(host)
        for host in getattr(settings, "TENANT_CENTRAL_HOSTS", ())
        if host and not host.startswith(("[", ".", "*."))
    }
    if hostname in central_hosts:
        raise ValidationError("This hostname is reserved for the platform's own system address.")
    suffix = platform_domain_suffix()
    if suffix and (hostname == suffix or hostname.endswith(f".{suffix}")):
        raise ValidationError("Use the platform subdomain option for domains under the platform domain.")
    domain, created = TenantDomain.objects.get_or_create(
        hostname=hostname,
        defaults={"tenant": tenant, "kind": TenantDomain.Kind.CUSTOM,
                  "status": TenantDomain.Status.PENDING,
                  "verification_token": secrets.token_urlsafe(24), "tls_status": "pending_dns"},
    )
    if not created:
        if domain.tenant_id != tenant.pk:
            raise ValidationError("This hostname is already assigned to another workspace.")
        if domain.kind != TenantDomain.Kind.CUSTOM:
            raise ValidationError("This hostname is reserved for platform subdomains.")
        if domain.status == TenantDomain.Status.DISABLED:
            domain.status = TenantDomain.Status.PENDING
            domain.verification_token = secrets.token_urlsafe(24)
            domain.tls_status = "pending_dns"
            domain.save(update_fields=["status", "verification_token", "tls_status", "updated_at"])
    cache.delete(f"tenant-domain:{hostname}")
    return domain


def verify_custom_domain(domain: TenantDomain) -> bool:
    """Prove control of a custom hostname using its unique DNS TXT challenge."""
    if domain.kind != TenantDomain.Kind.CUSTOM or not domain.verification_token:
        return False
    try:
        import dns.resolver
    except ImportError as exc:
        raise RuntimeError("Install the backend requirements to enable DNS ownership checks.") from exc
    try:
        answers = dns.resolver.resolve(f"_hotelnbarmgmt.{domain.hostname}", "TXT", lifetime=5)
    except Exception:
        return False
    expected = f"hotelnbarmgmt-domain-verification={domain.verification_token}"
    found = any(expected in "".join(
        part.decode() if isinstance(part, bytes) else str(part) for part in answer.strings
    ) for answer in answers)
    if not found:
        return False
    domain.status = TenantDomain.Status.VERIFIED
    domain.verified_at = timezone.now()
    domain.tls_status = "awaiting_certificate"
    domain.save(update_fields=["status", "verified_at", "tls_status", "updated_at"])
    return True
