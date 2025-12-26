from django.db import models


class AIPerson(models.Model):
    promptId = models.CharField(
        max_length=255,
        primary_key=True,
        db_column="prompt_id"
    )

    name = models.CharField(
        max_length=255,
        null=False,
        db_column="name"
    )

    era = models.CharField(
        max_length=255,
        null=False,
        db_column="era"
    )

    summary = models.TextField(
        null=True,
        blank=True,
        db_column="summary"
    )

    exQuestion = models.TextField(
        null=True,
        blank=True,
        db_column="ex_question"
    )

    greetingMessage = models.TextField(
        null=True,
        blank=True,
        db_column="greeting_message"
    )

    year = models.IntegerField(
        null=True,
        blank=True,
        db_column="year"
    )

    latitude = models.FloatField(
        null=True,
        blank=True,
        db_column="latitude"
    )

    longitude = models.FloatField(
        null=True,
        blank=True,
        db_column="longitude"
    )

    class Meta:
        db_table = "ai_person"
        managed = False
