# apps/notifications/migrations/0003_notification_updates.py
# Run: python manage.py makemigrations
# Then: python manage.py migrate

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_initial'),
        ('stock', '0001_initial'),
    ]

    operations = [
        # Add new notification types
        migrations.AlterField(
            model_name='notification',
            name='notification_type',
            field=models.CharField(
                choices=[
                    ('PROJECT_ASSIGNED', 'Assigned to Project'),
                    ('PROJECT_STARTING_SOON', 'Project Starting Soon'),
                    ('PROJECT_MODIFIED', 'Project Modified'),
                    ('PROJECT_DELETED', 'Project Deleted'),
                    ('MAINTENANCE_STARTING_SOON', 'Maintenance Starting Soon'),
                    ('MAINTENANCE_ADDED', 'Maintenance Added'),
                    ('MAINTENANCE_MODIFIED', 'Maintenance Modified'),
                    ('MAINTENANCE_DELETED', 'Maintenance Deleted'),
                    ('LOW_STOCK_ALERT', 'Low Stock Alert'),
                    ('OUT_OF_STOCK_ALERT', 'Out of Stock Alert'),
                ],
                db_index=True,
                max_length=50
            ),
        ),
        # Add related_product field
        migrations.AddField(
            model_name='notification',
            name='related_product',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='notifications',
                to='stock.product'
            ),
        ),
        # Add confirmation fields
        migrations.AddField(
            model_name='notification',
            name='is_confirmed',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name='notification',
            name='confirmed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='notification',
            name='last_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='notification',
            name='send_count',
            field=models.IntegerField(default=0),
        ),
        # Add new preferences
        migrations.AddField(
            model_name='notificationpreference',
            name='enable_low_stock_alert',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='notificationpreference',
            name='enable_out_of_stock_alert',
            field=models.BooleanField(default=True),
        ),
        # Add new index
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['is_confirmed', 'notification_type'], name='notificatio_is_conf_idx'),
        ),
    ]