from django.urls import path
from .views import cod_checkout, select_store, review_store, confirm_store, simulate_shipped, db_query_tool, simulate_cod_paid, 
    simulate_cvscod_paid, simulate_cvscod_failed, query_and_simulate_cod, mock_shipped, mock_created  # 【新增】

urlpatterns = [
    path("cod_checkout/", cod_checkout, name="cod_checkout"),
    path("select_store/", select_store, name="select_store"),
    path("review_store/", review_store, name="review_store"),   # 新增
    path("confirm_store/", confirm_store, name="confirm_store"),
    path("simulate_shipped/<str:merchant_trade_no>/", simulate_shipped, name="simulate_shipped"),        # 【新增】
    path("simulate_cod_paid/<str:merchant_trade_no>/", simulate_cod_paid, name="simulate_cod_paid"),      # 【新增】
    path("db_query_tool/", db_query_tool, name="db_query_tool"),  # 新增
    # 【新增】加進現有的 urlpatterns 裡
    path('query_and_simulate_cod/', query_and_simulate_cod, name='query_and_simulate_cod'),
    path('simulate_cvscod_paid/<str:merchant_trade_no>/', simulate_cvscod_paid, name='simulate_cvscod_paid'),
    path('simulate_cvscod_failed/<str:merchant_trade_no>/', simulate_cvscod_failed, name='simulate_cvscod_failed'),
    path('mock_shipped/<str:merchant_trade_no>/', mock_shipped, name='mock_shipped'),
	path('mock_created/<str:merchant_trade_no>/', mock_created, name='mock_created'),
]