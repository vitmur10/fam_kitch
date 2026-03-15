from django.db import models


class MenuDay(models.Model):
    date = models.DateField(unique=True)
    image = models.ImageField(upload_to="menu_days/", blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return str(self.date)


class MenuItem(models.Model):
    menu_day = models.ForeignKey(MenuDay, on_delete=models.CASCADE, related_name="items")
    title = models.CharField(max_length=80)

    full_title = models.CharField(max_length=80, default="Комплекс повністю")
    full_price = models.PositiveIntegerField()

    first_title = models.CharField(max_length=80, default="Перша страва")
    first_price = models.PositiveIntegerField(default=0)

    second_title = models.CharField(max_length=80, default="Друга страва")
    second_price = models.PositiveIntegerField(default=0)

    third_title = models.CharField(max_length=80, blank=True, default="")
    third_price = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.title} ({self.menu_day.date})"