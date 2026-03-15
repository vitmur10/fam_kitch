from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from .models import MenuDay, MenuItem
from .serializers import MenuItemSerializer


class ActiveMenuView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        date = request.query_params.get("date")

        qs = MenuDay.objects.filter(is_active=True)
        if date:
            qs = qs.filter(date=date)

        day = qs.order_by("date").first()
        if not day:
            return Response({"detail": "No active menu"}, status=404)

        items = (
            MenuItem.objects
            .filter(menu_day=day, is_active=True)
            .order_by("sort_order", "id")
        )

        image_url = None
        if day.image:
            image_url = request.build_absolute_uri(day.image.url)

        return Response({
            "day_id": day.id,
            "date": str(day.date),
            "image": image_url,
            "items": MenuItemSerializer(items, many=True).data
        })