from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0222_permanent_api_keys")]

    operations = [
        migrations.AddField(
            model_name="longrunningjob",
            name="recent_photos",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
