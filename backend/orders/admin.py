from django.contrib import admin
from .models import Customer, DeliveryLocation, Order, OrderLine


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("telegram_id", "phone", "username", "first_name", "is_subscribed", "created_at")
    search_fields = ("telegram_id", "phone", "username", "first_name")
    list_filter = ("is_subscribed", "created_at")


@admin.register(DeliveryLocation)
class DeliveryLocationAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "title")


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0
    readonly_fields = ("line_total",)
    fields = ("item_key_snapshot", "title_snapshot", "price_snapshot", "qty", "line_total")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer",
        "customer_username",
        "customer_first_name",
        "customer_phone",
        "menu_day",
        "location",
        "status",
        "total",
        "created_at",
    )
    list_filter = ("status", "menu_day", "location", "created_at")
    search_fields = (
        "id",
        "customer__telegram_id",
        "customer__phone",
        "customer__username",
        "customer__first_name",
    )
    inlines = [OrderLineInline]
    readonly_fields = ("subtotal", "total", "created_at")

    @admin.display(description="Username")
    def customer_username(self, obj):
        if obj.customer.username:
            return f"@{obj.customer.username}"
        return "-"

    @admin.display(description="Ім'я")
    def customer_first_name(self, obj):
        return obj.customer.first_name or "-"

    @admin.display(description="Телефон")
    def customer_phone(self, obj):
        return obj.customer.phone or "-"