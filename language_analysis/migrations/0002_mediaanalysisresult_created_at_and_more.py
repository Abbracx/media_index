# Generated by Django 5.1.2 on 2024-11-14 21:55

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("language_analysis", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="mediaanalysisresult",
            name="created_at",
            field=models.DateTimeField(default=datetime.datetime.now),
        ),
        migrations.AddField(
            model_name="mediaanalysisresult",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
