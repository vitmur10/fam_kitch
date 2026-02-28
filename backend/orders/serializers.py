from rest_framework import serializers
from .models import Customer, DeliveryLocation, Order, OrderLine
from menu.models import MenuDay, MenuItem


class CreateOrderSerializer(serializers.Serializer):
    telegram_id = serializers.IntegerField()
    phone = serializers.CharField(required=False, allow_blank=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    username = serializers.CharField(required=False, allow_blank=True)

    location_code = serializers.CharField()
    menu_day_id = serializers.IntegerField()

    # cart: {"full:<item_id>": qty, "p1:<item_id>": qty, ...}
    cart = serializers.DictField(child=serializers.IntegerField(min_value=1))

    comment = serializers.CharField(required=False, allow_blank=True)

    def _item_positions_from_model(self, item: MenuItem) -> dict:
        m = {}

        if getattr(item, "full_price", 0) and (item.full_title or "").strip():
            m[f"full:{item.id}"] = {"title": item.full_title, "price": int(item.full_price)}

        if getattr(item, "first_price", 0) and (item.first_title or "").strip():
            m[f"p1:{item.id}"] = {"title": item.first_title, "price": int(item.first_price)}

        if getattr(item, "second_price", 0) and (item.second_title or "").strip():
            m[f"p2:{item.id}"] = {"title": item.second_title, "price": int(item.second_price)}

        if getattr(item, "third_price", 0) and (item.third_title or "").strip():
            m[f"p3:{item.id}"] = {"title": item.third_title, "price": int(item.third_price)}

        return m

    def validate(self, attrs):
        try:
            attrs["location"] = DeliveryLocation.objects.get(code=attrs["location_code"], is_active=True)
        except DeliveryLocation.DoesNotExist:
            raise serializers.ValidationError({"location_code": "Unknown location"})

        try:
            attrs["menu_day"] = MenuDay.objects.get(id=attrs["menu_day_id"], is_active=True)
        except MenuDay.DoesNotExist:
            raise serializers.ValidationError({"menu_day_id": "Menu day not found"})

        items = list(
            MenuItem.objects
            .filter(menu_day=attrs["menu_day"], is_active=True)
            .order_by("sort_order", "id")
        )
        if not items:
            raise serializers.ValidationError({"menu_day_id": "No active items for this day"})

        key_map = {}
        for it in items:
            key_map.update(self._item_positions_from_model(it))

        cart_keys = list(attrs["cart"].keys())
        missing = [k for k in cart_keys if k not in key_map]
        if missing:
            raise serializers.ValidationError({"cart": f"Invalid items/positions for this day: {missing}"})

        attrs["key_map"] = key_map
        return attrs

    def create(self, validated):
        telegram_id = validated["telegram_id"]

        customer, _ = Customer.objects.get_or_create(
            telegram_id=telegram_id,
            defaults={
                "phone": validated.get("phone", ""),
                "first_name": validated.get("first_name", ""),
                "username": validated.get("username", ""),
            }
        )

        if validated.get("phone"):
            customer.phone = validated["phone"]
        if validated.get("first_name"):
            customer.first_name = validated["first_name"]
        if validated.get("username"):
            customer.username = validated["username"]
        customer.save()

        order = Order.objects.create(
            customer=customer,
            location=validated["location"],
            menu_day=validated["menu_day"],
            status=Order.Status.CONFIRMED,
            comment=validated.get("comment", ""),
        )

        subtotal = 0
        for key, qty in validated["cart"].items():
            meta = validated["key_map"][key]
            title = meta["title"]
            price = int(meta["price"])
            qty = int(qty)

            line_total = price * qty
            subtotal += line_total

            OrderLine.objects.create(
                order=order,
                item_key_snapshot=key,
                title_snapshot=title,
                price_snapshot=price,
                qty=qty,
                line_total=line_total,
            )

        order.subtotal = subtotal
        order.total = subtotal + order.delivery_fee
        order.save()

        return order


class CustomerSubscribeSerializer(serializers.Serializer):
    telegram_id = serializers.IntegerField()
    is_subscribed = serializers.BooleanField()

    def save(self, **kwargs):
        tg_id = self.validated_data["telegram_id"]
        is_sub = self.validated_data["is_subscribed"]

        customer, _ = Customer.objects.get_or_create(telegram_id=tg_id)
        customer.is_subscribed = is_sub
        customer.save()
        return customer