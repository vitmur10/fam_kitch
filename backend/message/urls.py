from django.urls import path
from .views import BotMessageView

urlpatterns = [
    path("messages/<slug:key>/", BotMessageView.as_view(), name="bot_message"),
]