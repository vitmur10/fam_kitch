from django.urls import path
from .views import wayforpay_callback

urlpatterns = [
    path("wayforpay/callback/", wayforpay_callback, name="wayforpay-callback"),
]