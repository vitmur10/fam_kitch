from django.contrib import admin
from django.db.models import Count
from .models import MenuDay, MenuItem


@admin.register(MenuDay)
class MenuDayAdmin(admin.ModelAdmin):
    list_display = ("date", "is_active", "items_count")
    list_filter = ("is_active", "date")
    ordering = ("-date",)
    date_hierarchy = "date"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(_items_count=Count("items"))

    @admin.display(description="Комплексів")
    def items_count(self, obj):
        return getattr(obj, "_items_count", 0)


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = (
        "menu_day", "sort_order", "title", "is_active",
        "full_title", "full_price",
        "first_title", "first_price",
        "second_title", "second_price",
        "third_title", "third_price",
    )
    list_filter = ("menu_day", "is_active")
    search_fields = ("title", "full_title", "first_title", "second_title", "third_title")
    ordering = ("menu_day__date", "sort_order", "id")
    list_select_related = ("menu_day",)

    list_editable = (
        "sort_order", "is_active",
        "full_title", "full_price",
        "first_title", "first_price",
        "second_title", "second_price",
        "third_title", "third_price",
    )
    list_display_links = ("title",)

    fieldsets = (
        ("День та порядок", {"fields": ("menu_day", "sort_order", "is_active")}),
        ("Назва комплексу", {"fields": ("title",)}),
        ("Повний комплекс", {"fields": ("full_title", "full_price")}),
        ("Позиції", {"fields": (("first_title", "first_price"),
                                ("second_title", "second_price"),
                                ("third_title", "third_price"))}),
    )