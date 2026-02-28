from django.contrib import admin
from .models import BotMessage


@admin.register(BotMessage)
class BotMessageAdmin(admin.ModelAdmin):
    list_display = ("key", "title", "is_active", "parse_mode", "updated_at")
    list_filter = ("is_active", "parse_mode")
    search_fields = ("key", "title", "text")
    ordering = ("key",)

