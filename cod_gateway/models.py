from django.db import models

# Create your models here.
from gateway.models import Order  # 只 import 共用 model,不修改 gateway app 任何檔案


class CODPaymentRequest(models.Model):
    """
    超商取貨付款(貨到付款, CVSCOD)請求。

    與 Order 建立 ForeignKey 關聯,因為兩者同屬 ecpay_mock 這個 Django 專案、
    同一個資料庫,關聯不會造成跨 Space 資料不同步的問題。
    一張 Order 理論上只會對應一筆 CODPaymentRequest(一個訂單只能選一種付款方式),
    所以用 OneToOneField 語意上更精準,但保留彈性(未來若要支援「重新選擇付款方式
    並保留歷史紀錄」)這裡先用 ForeignKey,並在建立時用 get_or_create 確保不會重複。
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,          # Order 被刪除時,對應的取貨付款紀錄一併清除
        related_name="cod_payment_requests",
        help_text="關聯到主訂單(同一家商店 E_commerce 的訂單)",
    )

    merchant_trade_no = models.CharField(max_length=50, unique=True)  # 對應 Order.order_number
    merchant_trade_date = models.DateTimeField()
    trade_amt = models.DecimalField(max_digits=10, decimal_places=2)
    item_name = models.TextField()
    receiver_name = models.CharField(max_length=100)
    receiver_address = models.CharField(max_length=255, blank=True, default="", verbose_name="收件地址", )

    receiver_cell_phone = models.CharField(max_length=20, blank=True, default="")

    LOGISTICS_SUBTYPE_CHOICES = [
        ("UNIMART", "7-ELEVEN"),
        ("FAMI", "全家"),
        ("HILIFE", "萊爾富"),
        ("OKMART", "OK超商"),
    ]
    logistics_subtype = models.CharField(
        max_length=10, choices=LOGISTICS_SUBTYPE_CHOICES, blank=True, default=""
    )

    # 使用者選定的取貨門市資訊(模擬電子地圖回傳的內容)
    store_id = models.CharField(max_length=20, blank=True, default="")
    store_name = models.CharField(max_length=100, blank=True, default="")
    store_address = models.CharField(max_length=200, blank=True, default="")
    store_lat = models.FloatField(blank=True, null=True)
    store_lng = models.FloatField(blank=True, null=True)

    status = models.CharField(
        max_length=20,
        choices=[
            ("cod_created", "待出貨"),
        ],
        default="cod_created",
    )

    check_mac_value = models.CharField(max_length=128, blank=True, null=True)
    return_url = models.URLField(blank=True, null=True)
    order_result_url = models.URLField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"CODPaymentRequest {self.merchant_trade_no} - {self.status}"