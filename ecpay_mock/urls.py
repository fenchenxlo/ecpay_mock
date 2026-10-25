"""
URL configuration for ecpay_mock project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView   # 【新增】首頁轉址

urlpatterns = [
    # 【新增】進入 127.0.0.1:8001/ 時，自動轉到 COD 查詢 + 模擬付款頁
    path(
        "",
        RedirectView.as_view(
            pattern_name="cod_gateway:query_and_simulate_cod",
            permanent=False,
        ),
        name="root_redirect",
    ),
    # 【新增】進入 127.0.0.1:8001/ 時，自動轉到 COD 查詢 + 模擬付款頁
    path(
        "atm/",
        RedirectView.as_view(
            pattern_name="gateway:query_and_simulate",
            permanent=False,
        ),
        name="root_redirect",
    ),
    path("admin/", admin.site.urls),
    path("gateway/", include("gateway.urls")),  # 把 gateway app 的 urls 串進來
    path("cod_gateway/", include("cod_gateway.urls")),  # 把 cod_gateway app 的 urls 串進來
]
