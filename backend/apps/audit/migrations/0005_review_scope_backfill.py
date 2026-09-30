import uuid
from django.db import migrations


def backfill(apps, schema_editor):
    Review = apps.get_model('audit', 'ExceptionReview')
    sources = {'cash_variance': apps.get_model('pos', 'PosShift'), 'refund': apps.get_model('pos', 'Refund'), 'low_stock': apps.get_model('inventory', 'StockBalance'), 'overdue_departure': apps.get_model('lodging', 'Reservation')}
    for review in Review.objects.using(schema_editor.connection.alias).filter(scope_outlet__isnull=True, scope_site__isnull=True).iterator():
        model = sources.get(review.kind)
        if model is None:
            continue
        try:
            identifier = uuid.UUID(review.entity_id)
        except (ValueError, TypeError):
            continue
        source = model.objects.using(schema_editor.connection.alias).filter(pk=identifier, tenant_id=review.tenant_id).first()
        if source is None:
            continue
        if review.kind == 'refund':
            review.scope_outlet_id = source.order.outlet_id
            review.source_url = f'/staff/orders/{source.order_id}/'
        elif review.kind == 'overdue_departure':
            review.scope_site_id = source.site_id
            review.source_url = f'/staff/lodging/reservations/{source.pk}/'
        else:
            review.scope_outlet_id = source.outlet_id
            review.source_url = f'/staff/management/shifts/{source.pk}/' if review.kind == 'cash_variance' else '/staff/inventory/?low_stock=1'
        review.save(update_fields=['scope_outlet', 'scope_site', 'source_url'])


class Migration(migrations.Migration):
    dependencies = [('audit', '0004_exceptionpolicy_discount_threshold_and_more'), ('pos', '0015_workstationpairing_rls'), ('inventory', '0001_initial'), ('lodging', '0001_initial')]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
