from django.db import models

# Create your models here.

from django.db import models


class BotMessage(models.Model):
    class ParseMode(models.TextChoices):
        NONE = "none", "None"
        HTML = "HTML", "HTML"
        MARKDOWN = "Markdown", "Markdown"

    key = models.SlugField(
        max_length=64,
        unique=True,
        help_text="Унікальний ключ, напр. welcome, ask_phone, menu_header"
    )
    title = models.CharField(
        max_length=120,
        blank=True,
        help_text="Назва для адмінки (щоб було зручно шукати)"
    )
    text = models.TextField(help_text="Текст повідомлення")
    parse_mode = models.CharField(
        max_length=16,
        choices=ParseMode.choices,
        default=ParseMode.HTML
    )
    is_active = models.BooleanField(default=True)
    comment = models.CharField(
        max_length=255,
        blank=True,
        help_text="Де використовується / підказка для контент-менеджера"
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Bot message"
        verbose_name_plural = "Bot messages"
        ordering = ["key"]

    def __str__(self):
        return f"{self.key}"