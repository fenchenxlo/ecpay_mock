from django.contrib import admin
from .models import Order, PaymentRequest, PaymentNotification

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "user_id", "amount", "status", "created_at")
    search_fields = ("order_number", "user_id")
    list_filter = ("status", "created_at")

@admin.register(PaymentRequest)
class PaymentRequestAdmin(admin.ModelAdmin):
    list_display = ("merchant_trade_no", "trade_amt", "payment_type", "trade_no", "return_url")
    search_fields = ("merchant_trade_no", "trade_no")
    list_filter = ("payment_type",)

@admin.register(PaymentNotification)
class PaymentNotificationAdmin(admin.ModelAdmin):
    list_display = ("merchant_trade_no", "trade_no", "trade_amt", "payment_type", "rtn_code")
    search_fields = ("merchant_trade_no", "trade_no")
    list_filter = ("payment_type", "rtn_code")