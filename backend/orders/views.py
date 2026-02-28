from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from rest_framework import serializers

from .serializers import CreateOrderSerializer, CustomerSubscribeSerializer
from .models import Order, OrderLine


class OrderLineOutSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderLine
        fields = ("item_key_snapshot", "title_snapshot", "price_snapshot", "qty", "line_total")


class OrderOutSerializer(serializers.ModelSerializer):
    lines = OrderLineOutSerializer(many=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "status",
            "menu_day_id",
            "location_id",
            "subtotal",
            "delivery_fee",
            "total",
            "created_at",
            "lines",
        )


class CreateOrderView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        ser = CreateOrderSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        order = ser.save()
        return Response(OrderOutSerializer(order).data, status=status.HTTP_201_CREATED)


class CustomerSubscribeView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        ser = CustomerSubscribeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        customer = ser.save()
        return Response({"ok": True, "telegram_id": customer.telegram_id, "is_subscribed": customer.is_subscribed})