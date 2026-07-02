from django.urls import path
from . import views

urlpatterns = [
    path("ecpay_gateway_checkout/", views.ecpay_gateway_checkout, name="ecpay_gateway_checkout"),  # 商城送資料 → 綠界
#     path("simulate_bank_paid/<str:merchant_trade_no>/", views.simulate_bank_paid, name="simulate_bank_paid"),
    path("simulate_bank_paid/", views.simulate_bank_paid, name="simulate_bank_paid"),
    path("payment_info/", views.payment_info, name="payment_info"),
    path("order_result/", views.order_result, name="order_result"),
    path("export_api_schema/", views.export_api_schema, name="export_api_schema"),
    path("download_orderPayment_json/", views.download_orderPayment_json, name="download_orderPayment_json"),
    
    path("checkout/", views.ecpay_checkout, name="ecpay_checkout"),  # 商城送資料 → 綠界  
#     path("createOrder/", views.createOrder, name="createOrder"),  # 商城送資料 → 綠界建立訂單
    path("pay/", views.ecpay_mock_pay, name="ecpay_mock_pay"),                 # 綠界付款頁 (ATM 虛擬帳號)
    path("notify/", views.ecpay_notify, name="ecpay_notify"),        # 綠界 server-to-server 回傳
]
