from decimal import Decimal

from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.models import Membership, MembershipRole
from apps.catalog.models import (
    MenuCategory,
    MenuItem,
    MenuItemModifierGroup,
    MenuItemOutlet,
    MenuItemRecipeLine,
    ModifierGroup,
    ServiceOffering,
    ServiceOfferingOption,
)
from apps.console.menu_sync import sync_menu_item_modifier_groups, sync_menu_item_outlet_links
from apps.inventory.models import StockMovement, StockReason
from apps.pos.models import Workstation
from apps.lodging.models import RoomRateWindow, RoomType
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY
from apps.tenants.business_lines import modules_for_business_lines
from apps.tenants.models import (
    BillingEvent,
    BillingEventType,
    BillingInvoice,
    BillingInvoiceStatus,
    Outlet,
    OutletType,
    Plan,
    Site,
    SubscriptionStatus,
    Tenant,
    TenantFeatureEntitlement,
    TenantOutletModulePolicy,
    TenantSettings,
    TenantSetupProgress,
    TenantSubscription,
)

User = get_user_model()


class MenuOutletSyncTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Sync Org", slug="sync-org")
        TenantSettings.objects.get_or_create(tenant=cls.tenant)

    def test_sync_preserves_price_override_when_outlet_still_selected(self) -> None:
        site = Site.objects.create(tenant=self.tenant, name="S1")
        outlet = Outlet.objects.create(site=site, name="O1", outlet_type=OutletType.BAR)
        cat = MenuCategory.objects.create(tenant=self.tenant, name="Cat")
        item = MenuItem.objects.create(
            tenant=self.tenant,
            category=cat,
            name="Item",
            unit_price=Decimal("10.00"),
        )
        MenuItemOutlet.objects.create(
            menu_item=item,
            outlet=outlet,
            price_override=Decimal("9.00"),
        )
        sync_menu_item_outlet_links(item, [outlet])
        link = MenuItemOutlet.objects.get(menu_item=item, outlet=outlet)
        self.assertEqual(link.price_override, Decimal("9.00"))


class MenuModifierSyncTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Mod Org", slug="mod-org")
        TenantSettings.objects.get_or_create(tenant=cls.tenant)

    def test_sync_modifier_groups_sets_order(self) -> None:
        cat = MenuCategory.objects.create(tenant=self.tenant, name="Cat")
        item = MenuItem.objects.create(
            tenant=self.tenant,
            category=cat,
            name="Burger",
            unit_price=Decimal("12.00"),
        )
        g2 = ModifierGroup.objects.create(tenant=self.tenant, name="Size")
        g1 = ModifierGroup.objects.create(tenant=self.tenant, name="Cheese")
        sync_menu_item_modifier_groups(item, [g1, g2])
        links = list(MenuItemModifierGroup.objects.filter(menu_item=item).order_by("sort_order"))
        self.assertEqual(len(links), 2)
        self.assertEqual(links[0].group_id, g1.id)
        self.assertEqual(links[0].sort_order, 0)
        self.assertEqual(links[1].group_id, g2.id)
        self.assertEqual(links[1].sort_order, 1)


class ConsoleRoutingTests(TestCase):
    def test_console_index_reverse(self) -> None:
        self.assertEqual(reverse("console-index"), "/console/")
        self.assertEqual(reverse("console-org-setup"), "/console/org/setup/")
        self.assertEqual(reverse("console-org-service-offerings"), "/console/org/services/")
        service_id = "00000000-0000-0000-0000-000000000001"
        option_id = "00000000-0000-0000-0000-000000000002"
        self.assertEqual(
            reverse("console-org-service-offering-options", kwargs={"service_id": service_id}),
            f"/console/org/services/{service_id}/packages/",
        )
        self.assertEqual(
            reverse(
                "console-org-service-offering-option-edit",
                kwargs={"service_id": service_id, "option_id": option_id},
            ),
            f"/console/org/services/{service_id}/packages/{option_id}/edit/",
        )
        group_id = "00000000-0000-0000-0000-000000000003"
        self.assertEqual(
            reverse("console-org-modifier-groups"),
            "/console/org/menu/modifier-groups/",
        )
        self.assertEqual(
            reverse("console-org-modifier-options", kwargs={"group_id": group_id}),
            f"/console/org/menu/modifier-groups/{group_id}/options/",
        )
        self.assertEqual(reverse("root-entry"), "/")

    def test_console_index_redirects_anonymous(self) -> None:
        r = self.client.get(reverse("console-index"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/staff/login", r.url)

    def test_root_entry_redirects_anonymous_to_staff_login(self) -> None:
        r = self.client.get(reverse("root-entry"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("staff-login"))

    def test_root_entry_redirects_authenticated_to_staff_dashboard(self) -> None:
        user = User.objects.create_user(email="root-auth@test.local", password="TestPass9!")
        self.client.force_login(user)
        r = self.client.get(reverse("root-entry"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("staff-dashboard"))

    def test_password_reset_confirm_without_token_shows_request_form(self) -> None:
        r = self.client.get(reverse("staff-password-reset-confirm"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "This recovery link is incomplete or invalid.")

    def test_password_reset_confirm_with_uid_token_shows_new_password_form(self) -> None:
        user = User.objects.create_user(email="pw-link@test.local", password="TestPass9!")
        uid = urlsafe_base64_encode(force_bytes(str(user.pk)))
        token = default_token_generator.make_token(user)
        r = self.client.get(f"{reverse('staff-password-reset-confirm')}?uid={uid}&token={token}")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Update my password")
        self.assertContains(r, "New password")


class ConsoleAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Console Org", slug="console-org")
        TenantSettings.objects.create(tenant=cls.tenant, business_lines=["bar"], enabled_staff_modules=["pos", "workspace"])

    def _login_with_tenant(self, user) -> None:
        self.client.force_login(user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s.save()

    def test_platform_operator_can_switch_console_workspace_without_membership(self) -> None:
        user = User.objects.create_superuser(
            email="co-platform-switch@test.local",
            password="TestPass9!",
        )
        second_tenant = Tenant.objects.create(name="Second Console Org", slug="second-console-org")
        TenantSettings.objects.create(
            tenant=second_tenant,
            business_lines=["bar"],
            enabled_staff_modules=["pos", "workspace"],
        )
        self.client.force_login(user)

        home = self.client.get(reverse("console-index"))
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "Switch workspace")
        self.assertContains(home, "Second Console Org")

        switched = self.client.post(
            reverse("console-select-tenant"),
            {"tenant_id": str(second_tenant.id), "next": reverse("console-index")},
        )
        self.assertEqual(switched.status_code, 302)
        self.assertEqual(self.client.session[STAFF_SESSION_TENANT_KEY], str(second_tenant.id))

        home = self.client.get(reverse("console-index"))
        self.assertEqual(home.status_code, 200)
        self.assertEqual(home.context["active_tenant"], second_tenant)
        self.assertContains(home, "Active workspace:</strong> Second Console Org")
        organization = self.client.get(reverse("console-org"))
        self.assertEqual(organization.status_code, 200)

    def test_non_platform_user_cannot_switch_to_workspace_without_membership(self) -> None:
        user = User.objects.create_user(email="co-switch-denied@test.local", password="TestPass9!")
        self.client.force_login(user)
        response = self.client.post(
            reverse("console-select-tenant"),
            {"tenant_id": str(self.tenant.id)},
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(STAFF_SESSION_TENANT_KEY, self.client.session)

    def test_org_overview_redirects_without_tenant_session(self) -> None:
        user = User.objects.create_user(email="co-no-tenant@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        self.client.force_login(user)
        r = self.client.get(reverse("console-org"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("staff-dashboard"))

    def test_org_overview_ok_for_owner(self) -> None:
        user = User.objects.create_user(email="co-owner@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        self._login_with_tenant(user)
        r = self.client.get(reverse("console-org"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'class="console-sidebar"')
        self.assertContains(r, "Administration navigation")
        self.assertContains(r, "Administration navigation")
        self.assertContains(r, "Operations workspace")
        self.assertContains(r, "Branches &amp; sections")
        self.assertContains(r, "Business setup")
        self.assertContains(r, "Guided setup")
        self.assertContains(r, "Setup progress")
        self.assertNotContains(r, "<strong>Fizo</strong>", html=False)

    def test_hospitality_directories_use_shared_design(self) -> None:
        user = User.objects.create_user(email="hospitality-directory@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=self.tenant, role=MembershipRole.OWNER)
        settings_obj = TenantSettings.objects.get(tenant=self.tenant)
        settings_obj.business_lines = ["bar", "lodging"]
        settings_obj.enabled_staff_modules = modules_for_business_lines(["bar", "lodging"])
        settings_obj.save(update_fields=["business_lines", "enabled_staff_modules", "updated_at"])
        self._login_with_tenant(user)
        for route, heading in (
            ("console-org-menu-items", "Menu items"),
            ("console-org-rooms", "Rooms"),
            ("console-org-room-types", "Room types"),
            ("console-org-room-rates", "Rate windows"),
        ):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'class="grocery-setup hospitality-directory"')
                self.assertContains(response, heading)
                self.assertContains(response, "hospitality-console-body")

    def test_price_upload_requires_its_own_file_field(self) -> None:
        from django.core.files.uploadedfile import SimpleUploadedFile

        user = User.objects.create_user(email="csv-isolation-test@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=self.tenant, role=MembershipRole.OWNER)
        TenantSettings.objects.filter(tenant=self.tenant).update(business_lines=["supermarket"])
        self._login_with_tenant(user)
        url = reverse("console-org-catalog-import")
        sample = self.client.get(url + "?sample=1")
        upload = SimpleUploadedFile("catalog-example.csv", sample.content, content_type="text/csv")
        response = self.client.post(url, {"action": "preview_prices", "file": upload})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required")
        self.assertNotContains(response, "Price CSV columns must be")

    def test_sample_catalog_csv_is_not_parsed_as_price_update(self) -> None:
        from django.core.files.uploadedfile import SimpleUploadedFile

        user = User.objects.create_user(email="csv-workflow-test@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=self.tenant, role=MembershipRole.OWNER)
        TenantSettings.objects.filter(tenant=self.tenant).update(business_lines=["supermarket"])
        self._login_with_tenant(user)
        sample = self.client.get(reverse("console-org-catalog-import") + "?sample=1")
        self.assertEqual(sample.status_code, 200)
        upload = SimpleUploadedFile("catalog-example.csv", sample.content, content_type="text/csv")
        response = self.client.post(reverse("console-org-catalog-import"), {
            "action": "preview", "file": upload,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "rows passed validation")
        self.assertNotContains(response, "Price CSV columns must be")
        self.assertEqual(MenuItem.objects.filter(tenant=self.tenant).count(), 0)

    def test_business_setup_uses_fizo_shell_not_legacy_staff_theme(self) -> None:
        user = User.objects.create_user(email="fizo-shell-check@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=self.tenant, role=MembershipRole.OWNER)
        TenantSettings.objects.filter(tenant=self.tenant).update(business_lines=["supermarket"])
        self._login_with_tenant(user)
        for route in ("console-org", "console-org-setup", "console-org-sites"):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "fizo-console-shell.css")
                self.assertContains(response, "fizo-shell-nav")
                self.assertNotContains(response, "staff/staff-theme.css")
                self.assertNotContains(response, "grocery-owner-console.css")

    def test_import_page_has_clean_title_and_canonical_theme(self) -> None:
        user = User.objects.create_user(email="fizo-import-style@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=self.tenant, role=MembershipRole.OWNER)
        TenantSettings.objects.filter(tenant=self.tenant).update(business_lines=["supermarket"])
        self._login_with_tenant(user)
        response = self.client.get(reverse("console-org-catalog-import"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<title>Import products")
        self.assertNotContains(response, "<title>Import products<div>")
        self.assertContains(response, "fizo-setup-area.css")
        self.assertNotContains(response, "grocery-owner-console.css")
        self.assertNotContains(response, "hospitality-console.css")

    def test_setup_directory_routes_use_fizo_layout(self) -> None:
        user = User.objects.create_user(email="fizo-directories@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=self.tenant, role=MembershipRole.OWNER)
        TenantSettings.objects.filter(tenant=self.tenant).update(business_lines=["supermarket"])
        self._login_with_tenant(user)
        site = Site.objects.create(tenant=self.tenant, name="Directory branch")
        cases = (
            ("console-org-sites", {}),
            ("console-org-outlets", {"site_id": site.id}),
            ("console-org-menu-categories", {}),
            ("console-org-menu-items", {}),
        )
        for route, kwargs in cases:
            with self.subTest(route=route):
                response = self.client.get(reverse(route, kwargs=kwargs))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "fizo-entity")
                self.assertContains(response, "fizo-setup-area.css")
                self.assertNotContains(response, "grocery-owner-console.css")

    def test_modifier_and_service_lists_use_unified_layout(self) -> None:
        user = User.objects.create_user(email="fizo-lists@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=self.tenant, role=MembershipRole.OWNER)
        TenantSettings.objects.filter(tenant=self.tenant).update(business_lines=["bar", "services"])
        self._login_with_tenant(user)
        for route in ("console-org-modifier-groups", "console-org-service-offerings"):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "fizo-entity-list-page")
                self.assertContains(response, "fizo-setup-area.css")
                self.assertNotContains(response, "grocery-owner-console.css")
                self.assertNotContains(response, "hospitality-console.css")

    def test_modifier_group_uses_fizo_form_without_old_css(self) -> None:
        user = User.objects.create_user(email="fizo-modifier-form@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=self.tenant, role=MembershipRole.OWNER)
        TenantSettings.objects.filter(tenant=self.tenant).update(business_lines=["bar"])
        self._login_with_tenant(user)
        response = self.client.get(reverse("console-org-modifier-group-create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "fizo-entity-form-page")
        self.assertContains(response, "fizo-setup-area.css")
        self.assertNotContains(response, "grocery-owner-console.css")
        self.assertNotContains(response, "hospitality-console.css")

    def test_fizo_setup_forms_do_not_render_legacy_layout(self) -> None:
        user = User.objects.create_user(email="fizo-forms@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=self.tenant, role=MembershipRole.OWNER)
        TenantSettings.objects.filter(tenant=self.tenant).update(business_lines=["supermarket"])
        self._login_with_tenant(user)
        site = Site.objects.create(tenant=self.tenant, name="Test branch")
        for route, kwargs in (
            ("console-org-site-create", {}),
            ("console-org-menu-category-create", {}),
            ("console-org-outlet-create", {"site_id": site.id}),
        ):
            with self.subTest(route=route):
                response = self.client.get(reverse(route, kwargs=kwargs))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "fizo-entity-form-page")
                self.assertContains(response, "fizo-setup-area.css")
                self.assertNotContains(response, "grocery-owner-console.css")
                self.assertNotContains(response, "hospitality-console.css")
                self.assertNotContains(response, "grocery-setup")

    def test_all_setup_routes_use_canonical_stylesheet(self) -> None:
        user = User.objects.create_user(email="setup-css-route@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=self.tenant, role=MembershipRole.OWNER)
        settings_obj = TenantSettings.objects.get(tenant=self.tenant)
        settings_obj.business_lines = ["supermarket"]
        settings_obj.save(update_fields=["business_lines", "updated_at"])
        self._login_with_tenant(user)
        routes = ("console-org-site-create", "console-org-menu-category-create")
        for route in routes:
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "fizo-setup-area.css")
                self.assertNotContains(response, "grocery-owner-console.css")

    def test_store_setup_renders_reference_layout_without_static_css(self) -> None:
        user = User.objects.create_user(email="fizo-reference-layout@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=self.tenant, role=MembershipRole.OWNER)
        settings_obj = TenantSettings.objects.get(tenant=self.tenant)
        settings_obj.business_lines = ["supermarket"]
        settings_obj.save(update_fields=["business_lines", "updated_at"])
        self._login_with_tenant(user)
        response = self.client.get(reverse("console-org-setup"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "fizo-setup-page")
        self.assertContains(response, "fizo-setup-area.css")
        self.assertNotContains(response, "fizo-setup-wizard.css")
        self.assertNotContains(response, "grocery-owner-console.css")
        self.assertContains(response, "grocery-setup__step-visual")
        self.assertContains(response, "Set up your store")
        self.assertContains(response, "Required setup progress")
        self.assertContains(response, "fizo-shell-nav")
        self.assertContains(response, self.tenant.name)

    def test_hospitality_setup_uses_unified_shell(self) -> None:
        user = User.objects.create_user(email="hospitality-shell@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=self.tenant, role=MembershipRole.OWNER)
        self._login_with_tenant(user)
        response = self.client.get(reverse("console-org-setup"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "hospitality-console-body")
        self.assertContains(response, "Set up your business")
        self.assertContains(response, "Hospitality management")
        self.assertNotContains(response, "grocery-console-body")

    def test_mixed_retail_and_hospitality_keeps_store_shell(self) -> None:
        settings_obj = TenantSettings.objects.get(tenant=self.tenant)
        settings_obj.business_lines = ["supermarket", "bar", "lodging"]
        settings_obj.save(update_fields=["business_lines", "updated_at"])
        user = User.objects.create_user(email="mixed-shell@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=self.tenant, role=MembershipRole.OWNER)
        self._login_with_tenant(user)
        response = self.client.get(reverse("console-org-setup"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "grocery-console-body")
        self.assertContains(response, "Set up your store")
        self.assertNotContains(response, "hospitality-console-body")

    def test_org_setup_shows_first_step_when_workspace_empty(self) -> None:
        user = User.objects.create_user(email="co-setup-empty@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        self._login_with_tenant(user)
        r = self.client.get(reverse("console-org-setup"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Create your first branch")
        self.assertContains(r, reverse("console-org-site-create"))
        prog = TenantSetupProgress.objects.get(tenant=self.tenant)
        self.assertEqual(prog.last_completion_percent, 16)  # Business profile is already configured.
        self.assertEqual(prog.last_next_step_key, "first_property")

    def test_setup_business_profile_limits_modules_and_admin_pages(self) -> None:
        user = User.objects.create_user(email="co-profile@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        self._login_with_tenant(user)
        response = self.client.post(
            reverse("console-org-setup"),
            {"business_lines": ["bar", "kitchen"]},
        )
        self.assertRedirects(response, reverse("console-org-setup"))
        settings_obj = TenantSettings.objects.get(tenant=self.tenant)
        self.assertEqual(settings_obj.business_lines, ["bar", "kitchen"])
        self.assertIn("pos", settings_obj.enabled_staff_modules)
        self.assertIn("kitchen", settings_obj.enabled_staff_modules)
        self.assertNotIn("lodging", settings_obj.enabled_staff_modules)
        self.assertNotIn("events", settings_obj.enabled_staff_modules)

        setup_page = self.client.get(reverse("console-org-setup"))
        self.assertContains(setup_page, "Kitchen / food preparation")
        self.assertNotContains(setup_page, "Lodging setup")

        rooms = self.client.get(reverse("console-org-rooms"))
        self.assertRedirects(rooms, reverse("console-org-setup"))

    def test_service_setup_is_hidden_and_protected_when_not_selected(self) -> None:
        settings_obj = TenantSettings.objects.get(tenant=self.tenant)
        settings_obj.business_lines = ["bar"]
        settings_obj.enabled_staff_modules = ["pos", "inventory", "purchasing", "finance", "workspace"]
        settings_obj.save(update_fields=["business_lines", "enabled_staff_modules", "updated_at"])
        user = User.objects.create_user(email="co-no-services@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=self.tenant, role=MembershipRole.OWNER)
        self._login_with_tenant(user)

        overview = self.client.get(reverse("console-org"))
        self.assertNotContains(overview, "Services &amp; packages")
        services = self.client.get(reverse("console-org-service-offerings"))
        self.assertRedirects(services, reverse("console-org-setup"))

    def test_org_setup_points_to_outlet_create_when_site_exists(self) -> None:
        user = User.objects.create_user(email="co-setup-site@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        site = Site.objects.create(tenant=self.tenant, name="Site A")
        self._login_with_tenant(user)
        r = self.client.get(reverse("console-org-setup"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(
            r,
            reverse("console-org-outlet-create", kwargs={"site_id": site.id}),
        )
        # Opening stock is required only after an inventory-tracked item exists.
        self.assertNotContains(r, "Record first stock receive")
        self.assertContains(r, "Add at least one sellable item or service")
        prog = TenantSetupProgress.objects.get(tenant=self.tenant)
        self.assertEqual(prog.last_next_step_key, "first_outlet")

    def test_org_setup_can_skip_and_reset_step_state(self) -> None:
        user = User.objects.create_user(email="co-setup-skip@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        self._login_with_tenant(user)
        skip = self.client.post(
            reverse("console-org-setup-step-state"),
            {"step_key": "first_team_invite", "state": "skipped"},
        )
        self.assertEqual(skip.status_code, 302)
        prog = TenantSetupProgress.objects.get(tenant=self.tenant)
        self.assertEqual(prog.step_state_overrides.get("first_team_invite"), "skipped")
        r = self.client.get(reverse("console-org-setup"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Skipped")
        prog.refresh_from_db()
        self.assertEqual(prog.last_next_step_key, "first_property")
        reset = self.client.post(
            reverse("console-org-setup-step-state"),
            {"step_key": "first_team_invite", "state": "reset"},
        )
        self.assertEqual(reset.status_code, 302)
        prog.refresh_from_db()
        self.assertNotIn("first_team_invite", prog.step_state_overrides)
        r2 = self.client.get(reverse("console-org-setup"))
        self.assertContains(r2, "Pending")
        prog.refresh_from_db()
        self.assertEqual(prog.last_next_step_key, "first_property")

    def test_org_setup_complete_when_site_outlet_category_and_receive_exist(self) -> None:
        user = User.objects.create_user(email="co-setup-done@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        site = Site.objects.create(tenant=self.tenant, name="Site B")
        outlet = Outlet.objects.create(site=site, name="Bar 1", outlet_type=OutletType.BAR)
        Workstation.objects.create(tenant=self.tenant, outlet=outlet, name="Main till", code="MAIN")
        cat = MenuCategory.objects.create(tenant=self.tenant, name="Food")
        item = MenuItem.objects.create(
            tenant=self.tenant,
            category=cat,
            name="Rice",
            unit_price=Decimal("2.00"),
        )
        StockMovement.objects.create(
            tenant=self.tenant,
            outlet=outlet,
            menu_item=item,
            quantity_change=Decimal("10"),
            reason=StockReason.RECEIVE,
            created_by=user,
            note="Initial stock receive",
        )
        self._login_with_tenant(user)
        r = self.client.get(reverse("console-org-setup"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Setup complete")
        self.assertContains(r, "Required setup progress")

    def test_org_forbidden_for_server_role(self) -> None:
        user = User.objects.create_user(email="co-server@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.SERVER,
        )
        self._login_with_tenant(user)
        r = self.client.get(reverse("console-org"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("console-index"))

    def test_platform_tenants_forbidden_without_flag(self) -> None:
        user = User.objects.create_user(email="co-plain@test.local", password="TestPass9!")
        self.client.force_login(user)
        r = self.client.get(reverse("console-platform-tenants"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("console-index"))

    def test_django_admin_forbidden_for_customer_admin_even_if_staff_flag_is_set(self) -> None:
        user = User.objects.create_user(
            email="co-admin-denied@test.local",
            password="TestPass9!",
            is_staff=True,
        )
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        self.client.force_login(user)
        r = self.client.get(reverse("admin:index"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("admin:login"), r.url)

    def test_django_admin_allowed_for_platform_staff(self) -> None:
        user = User.objects.create_user(
            email="co-admin-platform@test.local",
            password="TestPass9!",
            is_staff=True,
            is_platform_staff=True,
        )
        self.client.force_login(user)
        r = self.client.get(reverse("admin:index"))
        self.assertEqual(r.status_code, 200)

    def test_platform_tenants_ok_for_platform_staff(self) -> None:
        user = User.objects.create_user(
            email="co-platform@test.local",
            password="TestPass9!",
            is_platform_staff=True,
        )
        self.client.force_login(user)
        r = self.client.get(reverse("console-platform-tenants"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Customer workspaces")

    def test_platform_tenant_list_filters_and_shows_workspace_metrics(self) -> None:
        user = User.objects.create_user(
            email="co-platform-filter@test.local",
            password="TestPass9!",
            is_platform_staff=True,
        )
        paused = Tenant.objects.create(name="Paused Shop", slug="paused-shop", is_active=False)
        Plan.objects.create(name="Filter Plan", code="filter-plan")
        TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=Plan.objects.get(code="filter-plan"),
            status=SubscriptionStatus.ACTIVE,
        )
        self.client.force_login(user)
        response = self.client.get(reverse("console-platform-tenants"), {"q": "paused", "active": "paused"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Paused Shop")
        self.assertNotContains(response, "Sync Org")
        self.assertEqual(response.context["tenant_total"], 2)
        self.assertEqual(response.context["tenant_active"], 1)
        self.assertEqual(response.context["tenant_paused"], 1)
        self.assertEqual(response.context["object_list"].count(), 1)
        self.assertEqual(response.context["object_list"][0].id, paused.id)

    def test_platform_operator_can_pause_and_restore_tenant_access_with_audit(self) -> None:
        user = User.objects.create_user(
            email="co-platform-pause@test.local",
            password="TestPass9!",
            is_platform_staff=True,
        )
        self.client.force_login(user)
        url = reverse("console-platform-tenant-control-plane", kwargs={"tenant_id": self.tenant.id})
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Pause workspace")
        paused = self.client.post(url, {"toggle_tenant_access": "1"})
        self.assertEqual(paused.status_code, 302)
        self.tenant.refresh_from_db()
        self.assertFalse(self.tenant.is_active)
        pause_event = BillingEvent.objects.get(tenant=self.tenant, metadata__action="tenant_access_changed")
        self.assertTrue(pause_event.metadata["previous_is_active"])
        self.assertFalse(pause_event.metadata["is_active"])
        self.assertEqual(pause_event.actor_id, user.id)

        restored = self.client.post(url, {"toggle_tenant_access": "1"})
        self.assertEqual(restored.status_code, 302)
        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.is_active)
        self.assertEqual(
            BillingEvent.objects.filter(tenant=self.tenant, metadata__action="tenant_access_changed").count(),
            2,
        )

    def test_platform_operator_can_manage_plans(self) -> None:
        user = User.objects.create_user(
            email="co-plan@test.local",
            password="TestPass9!",
            is_platform_staff=True,
        )
        self.client.force_login(user)
        create = self.client.post(
            reverse("console-platform-plan-create"),
            {
                "name": "Starter",
                "code": "starter",
                "is_active": "on",
                "monthly_price": "49.00",
                "included_modules": ["pos", "kitchen", "workspace"],
                "notes": "",
            },
        )
        self.assertEqual(create.status_code, 302)
        plan = Plan.objects.get(code="starter")
        self.assertEqual(plan.name, "Starter")
        self.assertIn("pos", plan.included_modules)
        listing = self.client.get(reverse("console-platform-plans"))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, "Starter")

    def test_platform_operator_can_save_tenant_subscription_and_entitlements(self) -> None:
        user = User.objects.create_user(
            email="co-control@test.local",
            password="TestPass9!",
            is_platform_staff=True,
        )
        plan = Plan.objects.create(
            name="Control Plan",
            code="control-plan",
            included_modules=["pos", "workspace"],
        )
        self.client.force_login(user)
        sub = self.client.post(
            reverse("console-platform-tenant-control-plane", kwargs={"tenant_id": self.tenant.id}),
            {
                "save_subscription": "1",
                "sub-plan": str(plan.id),
                "sub-status": SubscriptionStatus.ACTIVE,
                "sub-started_at": "2026-01-01T00:00",
                "sub-trial_ends_at": "",
                "sub-current_period_ends_at": "",
                "sub-cancelled_at": "",
            },
        )
        self.assertEqual(sub.status_code, 302)
        tsub = TenantSubscription.objects.get(tenant=self.tenant)
        self.assertEqual(tsub.plan_id, plan.id)
        self.assertEqual(tsub.status, SubscriptionStatus.ACTIVE)
        ent = self.client.post(
            reverse("console-platform-tenant-control-plane", kwargs={"tenant_id": self.tenant.id}),
            {
                "save_entitlements": "1",
                "ent-module_pos": "on",
                "ent-module_kitchen": "",
                "ent-module_promotions": "",
                "ent-module_inventory": "",
                "ent-module_purchasing": "",
                "ent-module_lodging": "",
                "ent-module_events": "",
                "ent-module_workspace": "on",
            },
        )
        self.assertEqual(ent.status_code, 302)
        overrides = {
            row.module_key: row.is_enabled
            for row in TenantFeatureEntitlement.objects.filter(tenant=self.tenant)
        }
        self.assertIn("pos", overrides)
        self.assertIn("workspace", overrides)

    def test_control_plane_invoice_past_due_drives_subscription_past_due(self) -> None:
        user = User.objects.create_user(
            email="co-billing@test.local",
            password="TestPass9!",
            is_platform_staff=True,
        )
        plan = Plan.objects.create(name="Billing Plan", code="billing-plan")
        TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=plan,
            status=SubscriptionStatus.ACTIVE,
        )
        self.client.force_login(user)
        create_invoice = self.client.post(
            reverse("console-platform-tenant-control-plane", kwargs={"tenant_id": self.tenant.id}),
            {
                "create_invoice": "1",
                "inv-invoice_number": "INV-100",
                "inv-amount": "120.00",
                "inv-currency": "USD",
                "inv-status": BillingInvoiceStatus.ISSUED,
                "inv-issued_at": "",
                "inv-due_at": "",
                "inv-paid_at": "",
                "inv-external_ref": "",
                "inv-note": "Monthly billing",
            },
        )
        self.assertEqual(create_invoice.status_code, 302)
        inv = BillingInvoice.objects.get(tenant=self.tenant, invoice_number="INV-100")
        mark_due = self.client.post(
            reverse("console-platform-tenant-control-plane", kwargs={"tenant_id": self.tenant.id}),
            {
                "invoice_set_status": "1",
                "invoice_id": str(inv.id),
                "status": BillingInvoiceStatus.PAST_DUE,
            },
        )
        self.assertEqual(mark_due.status_code, 302)
        inv.refresh_from_db()
        self.assertEqual(inv.status, BillingInvoiceStatus.PAST_DUE)
        sub = TenantSubscription.objects.get(tenant=self.tenant)
        self.assertEqual(sub.status, SubscriptionStatus.PAST_DUE)
        self.assertTrue(
            BillingEvent.objects.filter(
                tenant=self.tenant,
                event_type=BillingEventType.SUBSCRIPTION_STATUS_CHANGED,
                new_subscription_status=SubscriptionStatus.PAST_DUE,
            ).exists(),
        )

    def test_control_plane_transition_past_due_to_suspended(self) -> None:
        user = User.objects.create_user(
            email="co-transition@test.local",
            password="TestPass9!",
            is_platform_staff=True,
        )
        plan = Plan.objects.create(name="Ops Plan", code="ops-plan")
        TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=plan,
            status=SubscriptionStatus.PAST_DUE,
        )
        self.client.force_login(user)
        r = self.client.post(
            reverse("console-platform-tenant-control-plane", kwargs={"tenant_id": self.tenant.id}),
            {
                "transition_subscription": "1",
                "trn-target_status": SubscriptionStatus.SUSPENDED,
                "trn-reason": "Grace period expired",
            },
        )
        self.assertEqual(r.status_code, 302)
        sub = TenantSubscription.objects.get(tenant=self.tenant)
        self.assertEqual(sub.status, SubscriptionStatus.SUSPENDED)
        self.assertTrue(
            BillingEvent.objects.filter(
                tenant=self.tenant,
                event_type=BillingEventType.SUBSCRIPTION_STATUS_CHANGED,
                previous_subscription_status=SubscriptionStatus.PAST_DUE,
                new_subscription_status=SubscriptionStatus.SUSPENDED,
            ).exists(),
        )

    def test_control_plane_one_click_provisions_supermarket_tenant(self) -> None:
        user = User.objects.create_user(
            email="co-super-provision@test.local",
            password="TestPass9!",
            is_platform_staff=True,
        )
        self.client.force_login(user)
        r = self.client.post(
            reverse("console-platform-tenant-control-plane", kwargs={"tenant_id": self.tenant.id}),
            {"provision_supermarket": "1"},
        )
        self.assertEqual(r.status_code, 302)
        sub = TenantSubscription.objects.get(tenant=self.tenant)
        self.assertEqual(sub.status, SubscriptionStatus.ACTIVE)
        self.assertEqual(sub.plan.code, "supermarket-core")
        settings_obj = TenantSettings.objects.get(tenant=self.tenant)
        self.assertEqual(
            settings_obj.enabled_staff_modules,
            ["pos", "inventory", "purchasing", "promotions", "workspace"],
        )
        self.assertTrue(
            Site.objects.filter(tenant=self.tenant, is_active=True).exists(),
        )
        self.assertTrue(
            Outlet.objects.filter(
                site__tenant=self.tenant,
                is_active=True,
                outlet_type=OutletType.SUPERMARKET,
            ).exists(),
        )
        overrides = {
            row.module_key: row.is_enabled
            for row in TenantFeatureEntitlement.objects.filter(tenant=self.tenant)
        }
        self.assertEqual(overrides.get("pos"), True)
        self.assertEqual(overrides.get("inventory"), True)
        self.assertEqual(overrides.get("purchasing"), True)
        self.assertEqual(overrides.get("promotions"), True)
        self.assertEqual(overrides.get("workspace"), True)
        self.assertEqual(overrides.get("lodging"), False)
        self.assertEqual(overrides.get("events"), False)
        self.assertEqual(overrides.get("kitchen"), False)
        progress = TenantSetupProgress.objects.get(tenant=self.tenant)
        self.assertEqual(progress.step_state_overrides.get("lodging_basics"), "skipped")
        self.assertFalse(progress.suppress_dashboard_prompt)
        self.assertEqual(progress.last_next_step_key, "first_menu_category")
        self.assertTrue(
            BillingEvent.objects.filter(
                tenant=self.tenant,
                event_type=BillingEventType.NOTE,
                metadata__provisioning_profile="supermarket-core",
            ).exists(),
        )
        self.assertTrue(
            TenantOutletModulePolicy.objects.filter(
                tenant=self.tenant,
                outlet_type=OutletType.SUPERMARKET,
                is_active=True,
            ).exists(),
        )

    def test_control_plane_can_save_outlet_module_policy(self) -> None:
        user = User.objects.create_user(
            email="co-outlet-policy@test.local",
            password="TestPass9!",
            is_platform_staff=True,
        )
        self.client.force_login(user)
        r = self.client.post(
            reverse("console-platform-tenant-control-plane", kwargs={"tenant_id": self.tenant.id}),
            {
                "save_outlet_policy": "1",
                "op-outlet_type": OutletType.SUPERMARKET,
                "op-is_active": "on",
                "op-module_pos": "on",
                "op-module_inventory": "on",
                "op-module_purchasing": "on",
                "op-module_promotions": "on",
                "op-module_workspace": "on",
                "op-module_kitchen": "",
                "op-module_lodging": "",
                "op-module_events": "",
            },
        )
        self.assertEqual(r.status_code, 302)
        policy = TenantOutletModulePolicy.objects.get(
            tenant=self.tenant,
            outlet_type=OutletType.SUPERMARKET,
        )
        self.assertTrue(policy.is_active)
        self.assertEqual(
            sorted(policy.enabled_modules),
            sorted(["pos", "inventory", "purchasing", "promotions", "workspace"]),
        )

    def test_control_plane_can_prefill_outlet_policy_from_preset(self) -> None:
        user = User.objects.create_user(
            email="co-outlet-preset@test.local",
            password="TestPass9!",
            is_platform_staff=True,
        )
        self.client.force_login(user)
        r = self.client.post(
            reverse("console-platform-tenant-control-plane", kwargs={"tenant_id": self.tenant.id}),
            {
                "prefill_outlet_policy": "1",
                "op-policy_preset": "restaurant",
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Preset applied")
        self.assertContains(r, 'name="op-outlet_type"')
        self.assertContains(r, 'value="restaurant" selected')
        self.assertContains(r, 'name="op-module_kitchen"')

    def test_owner_can_create_menu_category_and_item(self) -> None:
        user = User.objects.create_user(email="co-menu@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        self._login_with_tenant(user)
        r = self.client.post(
            reverse("console-org-menu-category-create"),
            {"name": "Beverages", "sort_order": "1", "is_active": "on"},
        )
        self.assertEqual(r.status_code, 302)
        cat = MenuCategory.objects.get(tenant=self.tenant, name="Beverages")
        r2 = self.client.post(
            reverse("console-org-menu-item-create"),
            {
                "category": str(cat.id),
                "name": "Coffee",
                "description": "",
                "sku": "",
                "barcode": "",
                "unit_of_measure": "each",
                "track_inventory": "",
                "reorder_level": "",
                "unit_price": "3.50",
                "tax_rate_percent": "",
                "is_active": "on",
                "kds_station": "",
                "consume_recipe_on_sale": "",
            },
        )
        self.assertEqual(r2.status_code, 302)
        self.assertTrue(MenuItem.objects.filter(tenant=self.tenant, name="Coffee").exists())

    def test_owner_can_upload_product_photo(self) -> None:
        import io
        import tempfile
        from PIL import Image

        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings

        user = User.objects.create_user(email="co-photo@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=self.tenant, role=MembershipRole.OWNER)
        self._login_with_tenant(user)
        category = MenuCategory.objects.create(tenant=self.tenant, name="Photo products")
        # Generate a valid small PNG in memory; no dependency on external files.
        output = io.BytesIO()
        Image.new("RGB", (2, 2), "white").save(output, format="PNG")
        png = output.getvalue()
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse("console-org-menu-item-create"),
                {
                    "category": str(category.pk),
                    "name": "Photo coffee",
                    "unit_of_measure": "each",
                    "unit_price": "4500.00",
                    "is_active": "on",
                    "product_image": SimpleUploadedFile("coffee.png", png, content_type="image/png"),
                },
            )
            self.assertEqual(response.status_code, 302)
            product = MenuItem.objects.get(tenant=self.tenant, name="Photo coffee")
            self.assertTrue(product.product_image.name.startswith("products/"))
            self.assertTrue(product.product_image.storage.exists(product.product_image.name))
            self.assertEqual(product.product_image_src, product.product_image.url)

    def test_phone_photo_upload_keeps_product_details_and_tenant_scope(self) -> None:
        import io
        import tempfile
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings

        user = User.objects.create_user(email="mobile-image@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=self.tenant, role=MembershipRole.OWNER)
        self._login_with_tenant(user)
        category = MenuCategory.objects.create(tenant=self.tenant, name="Imported stock")
        item = MenuItem.objects.create(tenant=self.tenant, category=category, name="Imported cup",
                                       unit_price="2500.00", sku="CUP-1")
        url = reverse("console-org-menu-item-photo", kwargs={"item_id": item.id})
        self.assertContains(self.client.get(url), "Imported cup")
        self.assertContains(self.client.get(reverse("console-org-menu-item-edit", kwargs={"item_id": item.id})),
                            "Copy phone link")
        self.assertContains(self.client.get(reverse("console-org-menu-items")), "Add photo")
        output = io.BytesIO()
        Image.new("RGB", (2, 2), "white").save(output, format="PNG")
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            uploaded = SimpleUploadedFile("cup.png", output.getvalue(), content_type="image/png")
            response = self.client.post(url, {"photo": uploaded})
            self.assertEqual(response.status_code, 302)
            item.refresh_from_db()
            self.assertTrue(item.product_image.name.startswith("products/"))
            self.assertEqual(item.sku, "CUP-1")
            self.assertEqual(item.unit_price, Decimal("2500.00"))
            status = self.client.get(url + "?status=1")
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status["Cache-Control"], "private, no-store")
            self.assertEqual(status.json()["image_key"], item.product_image.name)
            other = Tenant.objects.create(name="Other image tenant", slug="other-image-tenant")
            other_cat = MenuCategory.objects.create(tenant=other, name="Other")
            other_item = MenuItem.objects.create(tenant=other, category=other_cat, name="Private product",
                                                 unit_price="1.00")
            self.assertEqual(self.client.get(reverse("console-org-menu-item-photo", kwargs={"item_id": other_item.id})).status_code, 404)
            self.assertEqual(self.client.post(reverse("console-org-menu-item-photo", kwargs={"item_id": other_item.id}),
                                              {"photo": SimpleUploadedFile("other.png", output.getvalue(), content_type="image/png")}).status_code, 404)

    def test_desktop_edit_keeps_photo_uploaded_after_form_was_opened(self) -> None:
        import io
        import tempfile
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings

        owner = User.objects.create_user(email="co-photo-race@test.local", password="TestPass9!")
        Membership.objects.create(user=owner, tenant=self.tenant, role=MembershipRole.OWNER)
        self._login_with_tenant(owner)
        category = MenuCategory.objects.create(tenant=self.tenant, name="Photo sync")
        item = MenuItem.objects.create(tenant=self.tenant, category=category, name="Original",
                                       unit_price="3000.00")
        edit_url = reverse("console-org-menu-item-edit", kwargs={"item_id": item.id})
        self.assertEqual(self.client.get(edit_url).status_code, 200)
        image_data = io.BytesIO()
        Image.new("RGB", (2, 2), "white").save(image_data, format="PNG")
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            photo_url = reverse("console-org-menu-item-photo", kwargs={"item_id": item.id})
            photo = SimpleUploadedFile("photo.png", image_data.getvalue(), content_type="image/png")
            self.assertEqual(self.client.post(photo_url, {"photo": photo}).status_code, 302)
            item.refresh_from_db()
            filename = item.product_image.name
            changed = self.client.post(edit_url, {
                "category": str(category.id), "name": "Updated on desktop",
                "unit_of_measure": "each", "unit_price": "3500.00",
                "is_active": "on",
            })
            self.assertEqual(changed.status_code, 302)
            item.refresh_from_db()
            self.assertEqual(item.name, "Updated on desktop")
            self.assertEqual(item.product_image.name, filename)
            self.assertTrue(item.product_image.storage.exists(filename))

    def test_owner_can_create_service_offering(self) -> None:
        TenantSettings.objects.filter(tenant=self.tenant).update(business_lines=["bar", "services"])
        user = User.objects.create_user(email="co-services@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        site = Site.objects.create(tenant=self.tenant, name="Wellness")
        outlet = Outlet.objects.create(site=site, name="Spa", outlet_type=OutletType.BAR)
        self._login_with_tenant(user)
        r = self.client.post(
            reverse("console-org-service-offering-create"),
            {
                "name": "Sauna session",
                "description": "45 minute sauna",
                "default_price": "20.00",
                "tax_rate_percent": "",
                "duration_minutes": "45",
                "kds_station": "sauna",
                "is_active": "on",
                "outlets": [str(outlet.id)],
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertTrue(ServiceOffering.objects.filter(tenant=self.tenant, name="Sauna session").exists())

    def test_owner_can_create_service_package(self) -> None:
        TenantSettings.objects.filter(tenant=self.tenant).update(business_lines=["bar", "services"])
        user = User.objects.create_user(email="co-service-package@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        service = ServiceOffering.objects.create(
            tenant=self.tenant,
            name="Massage",
            default_price=Decimal("30.00"),
            kds_station="spa",
            is_active=True,
        )
        self._login_with_tenant(user)
        r = self.client.post(
            reverse("console-org-service-offering-option-create", kwargs={"service_id": service.id}),
            {
                "name": "Deep tissue 90m",
                "description": "Premium package",
                "price": "55.00",
                "duration_minutes": "90",
                "kds_station": "spa",
                "sort_order": "1",
                "is_active": "on",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertTrue(ServiceOfferingOption.objects.filter(service_offering=service, name="Deep tissue 90m").exists())

    def test_owner_can_create_rate_window(self) -> None:
        TenantSettings.objects.filter(tenant=self.tenant).update(business_lines=["bar", "lodging"])
        user = User.objects.create_user(email="co-rate@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        site = Site.objects.create(tenant=self.tenant, name="Hotel A")
        rt = RoomType.objects.create(tenant=self.tenant, site=site, name="Standard", max_occupancy=2)
        self._login_with_tenant(user)
        r = self.client.post(
            reverse("console-org-room-rate-create"),
            {
                "room_type": str(rt.id),
                "label": "Summer",
                "valid_from": "2026-06-01",
                "valid_to": "2026-08-31",
                "nightly_amount": "199.00",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertTrue(RoomRateWindow.objects.filter(room_type=rt, label="Summer").exists())

    def test_owner_can_add_recipe_line(self) -> None:
        user = User.objects.create_user(email="co-recipe@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        cat = MenuCategory.objects.create(tenant=self.tenant, name="Food")
        parent = MenuItem.objects.create(
            tenant=self.tenant,
            category=cat,
            name="Burger",
            unit_price=Decimal("12.00"),
        )
        ing = MenuItem.objects.create(
            tenant=self.tenant,
            category=cat,
            name="Patty",
            unit_price=Decimal("2.00"),
        )
        self._login_with_tenant(user)
        r = self.client.post(
            reverse("console-org-menu-item-recipe-create", kwargs={"item_id": parent.id}),
            {
                "ingredient_item": str(ing.id),
                "quantity_per_unit": "1.5",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertTrue(
            MenuItemRecipeLine.objects.filter(parent_item=parent, ingredient_item=ing).exists(),
        )

    def test_owner_can_create_site(self) -> None:
        user = User.objects.create_user(email="co-site@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.TENANT_ADMIN,
        )
        self._login_with_tenant(user)
        r = self.client.post(
            reverse("console-org-site-create"),
            {
                "name": "Main hotel",
                "address_line": "1 Main St",
                "city": "Testville",
                "country_code": "US",
                "is_active": "on",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Site.objects.filter(tenant=self.tenant, name="Main hotel").exists())
