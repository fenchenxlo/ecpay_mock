from django.urls import path
from .views import cod_checkout, select_store, review_store, confirm_store, simulate_shipped, simulate_cod_paid  # 【新增】

urlpatterns = [
    path("cod_checkout/", cod_checkout, name="cod_checkout"),
    path("select_store/", select_store, name="select_store"),
    path("review_store/", review_store, name="review_store"),   # 新增
    path("confirm_store/", confirm_store, name="confirm_store"),
    path("simulate_shipped/<str:merchant_trade_no>/", simulate_shipped, name="simulate_shipped"),        # 【新增】
    path("simulate_cod_paid/<str:merchant_trade_no>/", simulate_cod_paid, name="simulate_cod_paid"),      # 【新增】
]