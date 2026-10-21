from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from apps.tenants.domains import begin_custom_domain_verification, create_platform_domain
from apps.tenants.models import Tenant, TenantDomain

from apps.tenants.middleware import TenantDomainResolutionMiddleware


class TenantDomainResolutionMiddlewareHostTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _resolve(self, host):
        request = self.factory.get("/", HTTP_HOST=host)
        middleware = TenantDomainResolutionMiddleware(lambda _request: HttpResponse("ok"))
        return middleware(request)

    @override_settings(ALLOWED_HOSTS=["testserver"], TENANT_CENTRAL_HOSTS=["testserver"])
    def test_configured_testserver_bypasses_tenant_fqdn_validation(self):
        response = self._resolve("testserver")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    @override_settings(ALLOWED_HOSTS=["localhost"], TENANT_CENTRAL_HOSTS=["localhost"])
    def test_configured_localhost_with_port_is_allowed(self):
        response = self._resolve("localhost:8000")
        self.assertEqual(response.status_code, 200)

    @override_settings(ALLOWED_HOSTS=["127.0.0.1"], TENANT_CENTRAL_HOSTS=["127.0.0.1"])
    def test_configured_ipv4_central_host_is_allowed(self):
        response = self._resolve("127.0.0.1:8000")
        self.assertEqual(response.status_code, 200)

    @override_settings(ALLOWED_HOSTS=["[::1]"], TENANT_CENTRAL_HOSTS=["[::1]"])
    def test_configured_ipv6_central_host_is_allowed(self):
        response = self._resolve("[::1]:8000")
        self.assertEqual(response.status_code, 200)

    @override_settings(ALLOWED_HOSTS=["192.0.2.10"], TENANT_CENTRAL_HOSTS=[])
    def test_unconfigured_ip_host_fails_closed(self):
        response = self._resolve("192.0.2.10")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.content, b"Workspace domain is not configured")


@override_settings(
    ALLOWED_HOSTS=["testserver", ".pos.example.test", "shop.example.com", "unverified.example.com"],
    TENANT_CENTRAL_HOSTS=["testserver", "pos.example.test"],
    TENANT_PLATFORM_DOMAIN="pos.example.test",
)
class TenantDualDomainTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.tenant = Tenant.objects.create(name="Sennana", slug="sennana")
        TenantDomain.objects.create(
            tenant=self.tenant, hostname="sennana.pos.example.test",
            kind=TenantDomain.Kind.PLATFORM, status=TenantDomain.Status.ACTIVE,
        )
        TenantDomain.objects.create(
            tenant=self.tenant, hostname="shop.example.com",
            kind=TenantDomain.Kind.CUSTOM, status=TenantDomain.Status.ACTIVE,
        )
        TenantDomain.objects.create(
            tenant=self.tenant, hostname="unverified.example.com",
            kind=TenantDomain.Kind.CUSTOM, status=TenantDomain.Status.PENDING,
        )

    def _resolve(self, hostname):
        request = RequestFactory().get("/staff/login/", HTTP_HOST=hostname)
        def capture(req):
            return HttpResponse(str(getattr(getattr(req, "domain_tenant", None), "pk", "")))
        return TenantDomainResolutionMiddleware(capture)(request)

    def test_platform_subdomain_and_full_domain_resolve_same_tenant(self):
        for hostname in ("sennana.pos.example.test", "shop.example.com"):
            with self.subTest(hostname=hostname):
                response = self._resolve(hostname)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content.decode(), str(self.tenant.pk))
                self.assertIn("Host", response.get("Vary", ""))

    def test_unverified_custom_domain_is_denied(self):
        self.assertEqual(self._resolve("unverified.example.com").status_code, 404)

    def test_unregistered_platform_subdomain_is_denied(self):
        self.assertEqual(self._resolve("unknown.pos.example.test").status_code, 404)

    def test_inactive_tenant_denied_on_both_domains(self):
        self.tenant.is_active = False
        self.tenant.save(update_fields=["is_active"])
        cache.clear()
        for hostname in ("sennana.pos.example.test", "shop.example.com"):
            with self.subTest(hostname=hostname):
                self.assertEqual(self._resolve(hostname).status_code, 404)


@override_settings(TENANT_PLATFORM_DOMAIN="pos.example.test", TENANT_CENTRAL_HOSTS=["pos.example.test"])
class TenantDomainRegistrationTests(TestCase):
    def setUp(self):
        self.first = Tenant.objects.create(name="First", slug="first-store")
        self.second = Tenant.objects.create(name="Second", slug="second-store")

    def test_platform_subdomain_registration_is_idempotent(self):
        first = create_platform_domain(self.first)
        again = create_platform_domain(self.first)
        self.assertEqual(first.pk, again.pk)
        self.assertEqual(first.hostname, "first-store.pos.example.test")
        self.assertEqual(first.status, TenantDomain.Status.ACTIVE)

    def test_custom_apex_and_subdomain_can_coexist(self):
        apex = begin_custom_domain_verification(self.first, "Shop.Example.COM.")
        subdomain = begin_custom_domain_verification(self.first, "pos.shop.example.com")
        self.assertEqual(apex.hostname, "shop.example.com")
        self.assertEqual(subdomain.hostname, "pos.shop.example.com")
        self.assertEqual(apex.status, TenantDomain.Status.PENDING)
        self.assertEqual(subdomain.status, TenantDomain.Status.PENDING)

    def test_duplicate_custom_domain_cannot_be_claimed_by_another_tenant(self):
        begin_custom_domain_verification(self.first, "shop.example.com")
        with self.assertRaises(ValidationError):
            begin_custom_domain_verification(self.second, "shop.example.com")

    def test_platform_namespace_cannot_be_taken_as_custom_domain(self):
        for hostname in ("pos.example.test", "first-store.pos.example.test"):
            with self.subTest(hostname=hostname):
                with self.assertRaises(ValidationError):
                    begin_custom_domain_verification(self.first, hostname)
