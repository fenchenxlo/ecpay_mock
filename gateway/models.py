from django.db import models
from django.utils import timezone

# 🧾 訂單模型
class Order(models.Model):
    # 新增：訂單編號
    order_number = models.CharField(max_length=50, unique=True, editable=False, null=True, blank=True ) # 訂單編號
    user_id = models.IntegerField()                           # 使用者編號
    receiver_name = models.CharField(max_length=100, help_text="收件者姓名" )
    amount = models.DecimalField(max_digits=10, decimal_places=2)  # 訂單金額
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("paid", "Paid"),
            ("failed", "Failed"),
            ("cancelled", "Cancelled"),
            ("expired", "Expired"),
        ],
        default="Pending"
    )
    created_at = models.DateTimeField(auto_now_add=True)      # 建立時間
    updated_at = models.DateTimeField(auto_now=True)          # 更新時間

    def __str__(self):
        return f"Order {self.order_number} - {self.status}"


# 💳 付款請求模型
class PaymentRequest(models.Model):
    merchant_id = models.CharField(max_length=20)                  # 商店代號
    merchant_trade_no = models.CharField(max_length=50, unique=True)  # 訂單編號
    merchant_trade_date = models.DateTimeField()                   # 訂單建立時間
    trade_amt = models.DecimalField(max_digits=10, decimal_places=2)  # 訂單總金額
    trade_desc = models.CharField(max_length=200, default="購買商品")    # 交易描述
    item_name = models.TextField()                                 # 商品名稱清單 (字串)
    payment_type = models.CharField(max_length=20)               # 交易類型 固定填 aio
    choose_payment = models.CharField(max_length=20)               # 使用者選擇的付款方式
    trade_no = models.CharField(max_length=50, blank=True, null=True)  # 模擬交易編號
    bank_code = models.CharField(max_length=3)                    # 銀行代碼
    v_account = models.CharField(max_length=20)                    # 虛擬銀行帳戶 (通常14-16)
    expire_date = models.DateTimeField(max_length=20, default=timezone.now)    # 繳費期限
    status = models.CharField(
        max_length=20,
        choices=[
            ("atm_pending", "ATM_Pending"),
            ("atm_created", "ATM_Create"),
            ("atm_paid", "ATM_Paid"),
            ("atm_failed", "ATM_Failed"),
            ("atm_cancelled", "ATM_Cancelled"),
            ("atm_expired", "ATM_Expired"),
        ],
        default="ATM_Pending"
    )
    
    check_mac_value = models.CharField(max_length=128, blank=True, null=True)

#     order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payment_requests")
    
    return_url = models.URLField(blank=True, null=True)               # 綠界回傳 URL
    payment_info_url = models.URLField(blank=True, null=True)         # 綠界通知商城已取虛擬帳號
    order_result_url = models.URLField(blank=True, null=True)      # 瀏覽器跳轉 URL


    def __str__(self):
        return f"PaymentRequest {self.merchant_trade_no}"


# 📩 綠界通知模型
class PaymentNotification(models.Model):
    merchant_trade_no = models.CharField(max_length=50)               # 商店訂單編號
    trade_no = models.CharField(max_length=50)                        # 綠界交易編號
    trade_amt = models.DecimalField(max_digits=10, decimal_places=2)  # 交易金額
    payment_date = models.DateTimeField()                             # 付款完成時間
    choose_payment = models.CharField(max_length=20)                   # 使用者選擇的付款方式
    payment_type = models.CharField(max_length=20)                    # 付款方式
    rtn_code = models.IntegerField()                                  # 回傳代碼 (1=成功)
    rtn_msg = models.CharField(max_length=100)                        # 回傳訊息
    simulate_paid = models.BooleanField(default=False)                # 測試付款標記

    def __str__(self):
        return f"Notification {self.trade_no} - Code {self.rtn_code}"
