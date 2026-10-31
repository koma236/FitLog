import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("social", "0001_initial"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="Follow",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("followee", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="incoming_follows", to=settings.AUTH_USER_MODEL)),
                ("follower", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="outgoing_follows", to=settings.AUTH_USER_MODEL)),
            ],
            options={"constraints": [
                models.UniqueConstraint(fields=("follower", "followee"), name="social_follow_pair"),
                models.CheckConstraint(condition=~models.Q(follower=models.F("followee")), name="social_follow_not_self"),
            ]},
        ),
    ]
