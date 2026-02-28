from rest_framework import serializers
from .models import MenuItem


class MenuItemSerializer(serializers.ModelSerializer):
    positions = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = ("id", "title", "positions")

    def get_positions(self, obj: MenuItem):
        positions = []

        if getattr(obj, "full_price", 0) > 0:
            positions.append({
                "key": f"full:{obj.id}",
                "title": obj.full_title,
                "price": obj.full_price,
            })

        if getattr(obj, "first_price", 0) > 0 and (obj.first_title or "").strip():
            positions.append({
                "key": f"p1:{obj.id}",
                "title": obj.first_title,
                "price": obj.first_price,
            })

        if getattr(obj, "second_price", 0) > 0 and (obj.second_title or "").strip():
            positions.append({
                "key": f"p2:{obj.id}",
                "title": obj.second_title,
                "price": obj.second_price,
            })

        if getattr(obj, "third_price", 0) > 0 and (obj.third_title or "").strip():
            positions.append({
                "key": f"p3:{obj.id}",
                "title": obj.third_title,
                "price": obj.third_price,
            })

        return positions