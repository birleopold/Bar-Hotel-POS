from pathlib import Path
import tempfile

from django.test import TestCase, override_settings
from django.urls import reverse


class ConfigPublicRouteTests(TestCase):
    def test_root_entry_is_safe_method_only(self):
        response = self.client.get(reverse("root-entry"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("staff-login"))

        denied = self.client.post(reverse("root-entry"))
        self.assertEqual(denied.status_code, 405)
        self.assertIn("GET", denied["Allow"])
        self.assertIn("HEAD", denied["Allow"])

    def test_public_product_media_serves_only_safe_requests(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            product_dir = Path(media_root) / "products"
            product_dir.mkdir(parents=True)
            asset = product_dir / "route-test.png"
            asset.write_bytes(b"route-media")

            url = reverse("public-product-media", kwargs={"path": "route-test.png"})
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), b"route-media")
            self.assertEqual(response["X-Content-Type-Options"], "nosniff")
            self.assertIn("public", response["Cache-Control"])

            denied = self.client.post(url, data={"replace": "1"})
            self.assertEqual(denied.status_code, 405)
            self.assertIn("GET", denied["Allow"])
            self.assertIn("HEAD", denied["Allow"])
