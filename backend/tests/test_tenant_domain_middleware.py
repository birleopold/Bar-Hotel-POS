from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

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
