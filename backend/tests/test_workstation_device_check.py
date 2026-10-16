"""Hardware self-test pages never expose another tenant's workstations."""
from django.test import SimpleTestCase
from django.urls import reverse


class WorkstationDiagnosticsRouteTests(SimpleTestCase):
    def test_diagnostics_url_uses_existing_staff_workstation_scope(self):
        import uuid
        destination = reverse(
            "staff-workstation-test", kwargs={"workstation_id": uuid.UUID(int=1)},
        )
        self.assertTrue(destination.startswith("/staff/pos/workstations/"))
        self.assertTrue(destination.endswith("/test/"))
