# ============================================================
# ECPay Mock
# gateway/urls.py
# ============================================================

from django.urls import path

from gateway.views import (
    home,
    ecpay_gateway_checkout,
    simulate_bank_paid,
    payment_info,
    payment_notify,
    cancel_order,   # 【新增】取消 ATM 訂單
    order_result,
    download_orderPayment_json,
    query_and_simulate,
    db_query_tool,
	atm_info,
)

app_name = "gateway"

urlpatterns = [

    # ========================================================
    # 【保留】
    # ECPay Mock 首頁
    # ========================================================

    path(
        "",
        home,
        name="home",
    ),

    # ========================================================
    # 【保留】
    # Store → ECPay Mock
    #
    # 正式 ATM 建立入口
    # ========================================================

    path(
        "ecpay_gateway_checkout/",
        ecpay_gateway_checkout,
        name="ecpay_gateway_checkout",
    ),

    # ========================================================
    # 【保留】
    #
    # 獨立的銀行付款模擬功能。
    #
    # 注意：
    # 這不是舊 checkout 流程，
    # 所以不能因為清理舊程式而刪掉。
    # ========================================================

    path(
        "simulate_bank_paid/",
        simulate_bank_paid,
        name="simulate_bank_paid",
    ),

    # ========================================================
    # 【保留】
    # ECPay Mock Payment Query
    # ========================================================

    path(
        "payment_info/",
        payment_info,
        name="payment_info",
    ),

    # ============================================================
    # 【新增】
    # Ecpay Mock ATM 資訊顯示
    # ============================================================

    path(
        "atm_info/",
        atm_info,
        name="atm_info",
    ),

    # ========================================================
    # 【保留】
    #
    # Bank Mock → ECPay Mock
    #
    # ATM 付款結果 Callback
    # ========================================================

    path(
        "payment_notify/",
        payment_notify,
        name="payment_notify",
    ),

    # 【新增】E_commerce 取消 ATM 訂單（POST + CheckMacValue）
    path(
        "cancel_order/",
        cancel_order,
        name="cancel_order",
    ),

    # ========================================================
    # 【保留】
    # Order Result
    # ========================================================

    path(
        "order_result/",
        order_result,
        name="order_result",
    ),

    # ========================================================
    # 【保留】
    # Debug / JSON 資料輸出
    # ========================================================

    path(
        "download_orderPayment_json/",
        download_orderPayment_json,
        name="download_orderPayment_json",
    ),

    # ========================================================
    # 【保留】
    # Admin DB Query Tool
    # ========================================================

    path(
        "admin-tools/query/",
        db_query_tool,
        name="db_query_tool",
    ),
    path("admin-tools/query_and_simulate/", query_and_simulate, name="query_and_simulate"),  # 新增:查詢+模擬付款合併頁

    # ========================================================
    # 【刪除/移出】
    #
    # 舊 checkout endpoint
    #
    # path(
    #     "checkout/",
    #     ecpay_checkout,
    #     name="ecpay_checkout",
    # ),
    #
    # 原因：
    # 正式 ATM 建立已統一使用：
    #
    #     /ecpay_gateway_checkout/
    # ========================================================

    # ========================================================
    # 【刪除/移出】
    #
    # 舊 ATM pay endpoint
    #
    # path(
    #     "pay/",
    #     ecpay_mock_pay,
    #     name="ecpay_mock_pay",
    # ),
    #
    # 原因：
    # ATM 流程已進入新的
    # Service / Gateway / Adapter 架構。
    # ========================================================

    # ========================================================
    # 【刪除/移出】
    #
    # 舊 notify endpoint
    #
    # path(
    #     "notify/",
    #     ecpay_notify,
    #     name="ecpay_notify",
    # ),
    #
    # 原因：
    # callback 統一使用：
    #
    #     /payment_notify/
    # ========================================================

    # ========================================================
    # 【刪除/移出】
    #
    # 舊 notify_bank endpoint
    #
    # path(
    #     "notify_bank/",
    #     notify_bank,
    #     name="notify_bank",
    # ),
    #
    # 原因：
    # 舊版 View 直接 httpx.post()
    # 並直接處理 Bank Mock。
    # 新架構禁止這種寫法。
    # ========================================================

]