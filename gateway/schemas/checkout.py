# ============================================================
# ECPay Mock
# gateway/schemas/checkout.py
# ============================================================

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import (
    ConfigDict,
    Field,
    field_validator,
)
from ninja import Schema


class ECPayCheckoutSchema(Schema):
    """
    【新增】

    ECPay Mock ATM Checkout Request Schema。

    ============================================================
    使用位置
    ============================================================

    E_commerce
        ↓
    HTTPX POST
        ↓
    /gateway/ecpay_gateway_checkout/
        ↓
    View
        ↓
    CheckMacValue 驗證
        ↓
    ECPayCheckoutSchema
        ↓
    ECPayService

    ============================================================
    注意
    ============================================================

    本 Schema 是：

        E_commerce → Ecpay Mock

    的 Request Contract。

    不是：

        Store models

    也不是：

        Bank Mock Request Schema。
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    # ========================================================
    # 【新增】
    # 商店訂單編號
    # ========================================================

    merchant_trade_no: str = Field(
        min_length=1,
        max_length=50,
    )

    # ========================================================
    # 【新增】
    # 交易金額
    # ========================================================

    trade_amt: Decimal = Field(
        gt=0,
    )

    # ========================================================
    # 【新增】
    # 商品名稱
    # ========================================================

    item_name: str = Field(
        default="購買商品",
        min_length=1,
        max_length=400,
    )

    # ========================================================
    # 【新增】
    # 付款方式
    #
    # 目前 ECPay Mock 這條流程只處理 ATM。
    # ========================================================

    choose_payment: str = Field(
        default="ATM",
        min_length=1,
        max_length=20,
    )

    # ========================================================
    # 【新增】
    # ECPay Merchant ID
    # ========================================================

    merchant_id: Optional[str] = Field(
        default="2000132",
        max_length=20,
    )

    # ========================================================
    # 【新增】
    # 商店交易時間
    # ========================================================

    merchant_trade_date: Optional[datetime] = (
        None
    )

    # ========================================================
    # 【新增】
    # 交易描述
    # ========================================================

    trade_desc: Optional[str] = Field(
        default="購買商品",
        max_length=200,
    )

    # ========================================================
    # 【新增】
    # ECPay payment type
    #
    # 目前 Mock 流程使用 aio。
    # ========================================================

    payment_type: Optional[str] = Field(
        default="aio",
        max_length=20,
    )

    # ========================================================
    # 【新增】
    # ECPay 回傳相關 URL
    #
    # 目前保留為 optional，
    # 因為不是 ATM 建立本身的必要欄位。
    # ========================================================

    # ========================================================
    # 【新增】建立 ecpay_mock Order 紀錄所需欄位
    # （schema 為 extra="forbid"，沒宣告的欄位會被擋）
    # ========================================================
    user_id: Optional[int] = None

    receiver_name: Optional[str] = Field(
        default=None,
        max_length=100,
    )

    ReturnURL: Optional[str] = None

    PaymentInfoURL: Optional[str] = None

    OrderResultURL: Optional[str] = None

    # ========================================================
    # 【新增】
    # Store → Ecpay Mock 的 CheckMacValue
    #
    # View 在進入 Service 前驗證。
    #
    # Schema 只保存資料格式，
    # 不負責 MAC 計算或驗證。
    # ========================================================

    CheckMacValue: str = Field(
        min_length=1,
        max_length=128,
    )

    # ========================================================
    # 【新增】
    # choose_payment validator
    # ========================================================

    @field_validator(
        "choose_payment"
    )
    @classmethod
    def validate_choose_payment(
        cls,
        value: str,
    ) -> str:
        """
        【新增】

        目前 ECPay Mock ATM checkout
        僅允許 ATM。
        """

        value = value.strip().upper()

        if value != "ATM":
            raise ValueError(
                "目前 ECPay Mock 僅支援 ATM"
            )

        return value

    # ========================================================
    # 【新增】
    # merchant_trade_no validator
    # ========================================================

    @field_validator(
        "merchant_trade_no"
    )
    @classmethod
    def validate_merchant_trade_no(
        cls,
        value: str,
    ) -> str:
        """
        【新增】

        清除前後空白，
        避免相同訂單因空白造成比對問題。
        """

        value = value.strip()

        if not value:
            raise ValueError(
                "merchant_trade_no 不可為空"
            )

        return value

    # ========================================================
    # 【新增】
    # trade_amt validator
    # ========================================================

    @field_validator(
        "trade_amt"
    )
    @classmethod
    def validate_trade_amt(
        cls,
        value: Decimal,
    ) -> Decimal:
        """
        【新增】

        再確認交易金額必須大於 0。
        """

        if value <= 0:
            raise ValueError(
                "trade_amt 必須大於 0"
            )

        return value