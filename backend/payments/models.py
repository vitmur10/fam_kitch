from django.db import models

class Payment(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "Created"
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    # ВАЖЛИВО: у тебе order модель в app "orders".
    # Замінити "orders.Order" якщо модель називається інакше.
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="payments")
    telegram_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    notified = models.BooleanField(default=False)
    provider = models.CharField(max_length=32, default="wayforpay")
    order_reference = models.CharField(max_length=64, unique=True)  # те що піде в WayForPay (можна = order.id)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=8, default="UAH")

    invoice_url = models.URLField(blank=True, null=True)
    transaction_status = models.CharField(max_length=64, blank=True, default="")
    reason_code = models.CharField(max_length=32, blank=True, default="")

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CREATED)

    raw_callback = models.JSONField(blank=True, null=True)  # щоб дебажити
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment({self.provider}) #{self.order_reference} {self.status}"