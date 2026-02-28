from django.db import models


class Customer(models.Model):
    telegram_id = models.BigIntegerField(unique=True)
    phone = models.CharField(max_length=32, blank=True, default="")
    first_name = models.CharField(max_length=128, blank=True, default="")
    username = models.CharField(max_length=128, blank=True, default="")

    location_code = models.CharField(max_length=32, blank=True, default="")

    is_subscribed = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.telegram_id} ({self.phone})"


class DeliveryLocation(models.Model):
    code = models.CharField(max_length=32, unique=True)   # "T1"
    title = models.CharField(max_length=128)              # "Вхід" etc
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} — {self.title}"


class Order(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"
        DONE = "done", "Done"

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders")
    location = models.ForeignKey(DeliveryLocation, on_delete=models.PROTECT, related_name="orders")

    # MenuDay з app menu
    menu_day = models.ForeignKey("menu.MenuDay", on_delete=models.PROTECT, related_name="orders")

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    comment = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order #{self.pk} ({self.customer.telegram_id})"


class OrderLine(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")

    # зберігаємо що саме замовили (ключ з бота, опційно)
    item_key_snapshot = models.CharField(max_length=64, blank=True, default="")

    title_snapshot = models.CharField(max_length=255)
    price_snapshot = models.DecimalField(max_digits=10, decimal_places=2)

    qty = models.PositiveIntegerField(default=1)
    line_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        self.line_total = (self.price_snapshot or 0) * self.qty
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title_snapshot} x{self.qty}"