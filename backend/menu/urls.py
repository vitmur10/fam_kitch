from django.urls import path
from .views import ActiveMenuView

urlpatterns = [
    path("menu/active/", ActiveMenuView.as_view()),
]