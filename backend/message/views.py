from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from .services import get_bot_message


class BotMessageView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, key: str):
        data = get_bot_message(key)

        if not data:
            return Response(
                {"detail": f"Message '{key}' not found"},
                status=404
            )

        return Response(data)