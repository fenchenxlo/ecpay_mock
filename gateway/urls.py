from django.urls import path,include
from gateway.views import (
    ecpay_gateway_checkout,
    simulate_bank_paid,
    payment_info,
    order_result,
#     export_api_schema,
    download_orderPayment_json,
    ecpay_checkout,
    notify_bank,
    payment_notify,
#     create_atm_order,
#     createOrder,
    ecpay_mock_pay,
    ecpay_notify,  
)

urlpatterns = [
    path("ecpay_gateway_checkout/", ecpay_gateway_checkout, name="ecpay_gateway_checkout"),  # 商城送資料 → 綠界
#     path("simulate_bank_paid/<str:merchant_trade_no>/", simulate_bank_paid, name="simulate_bank_paid"),
    path("simulate_bank_paid/", simulate_bank_paid, name="simulate_bank_paid"),
    path("notify_bank/", notify_bank, name="notify_bank"),
    path("payment_notify/", payment_notify, name="payment_notify"),
#     path("create_atm_order/", create_atm_order, name="create_atm_order"),
    path("payment_info/", payment_info, name="payment_info"),
    path("order_result/", order_result, name="order_result"),
#     path("export_api_schema/", export_api_schema, name="export_api_schema"),
    path("download_orderPayment_json/", download_orderPayment_json, name="download_orderPayment_json"),
    
    path("checkout/", ecpay_checkout, name="ecpay_checkout"),  # 商城送資料 → 綠界  
#     path("createOrder/", createOrder, name="createOrder"),  # 商城送資料 → 綠界建立訂單
    path("pay/", ecpay_mock_pay, name="ecpay_mock_pay"),                 # 綠界付款頁 (ATM 虛擬帳號)
    path("notify/", ecpay_notify, name="ecpay_notify"),        # 綠界 server-to-server 回傳
]