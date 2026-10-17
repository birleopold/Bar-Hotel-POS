"""Join independent receiving-review and in-transit migrations.

Both features branched from inventory.0012 while separate implementation
sessions were committing. Keep both irreversible migration histories intact.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0013_staged_transfer_receipts"),
        ("inventory", "0013_stocktransferreceipt_review"),
    ]

    operations = []
