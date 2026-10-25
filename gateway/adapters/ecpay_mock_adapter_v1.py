# commerce_shop/gateways/ecpay_mock_adapter.py

import uuid
import hashlib

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from .ecpay_gateway import (
    ECPayGateway,
    ECPayATMResult,
)


class ECPayMockAdapter(ECPayGateway):
    """
    綠界 Mock Adapter

    用來模擬：

        商城
          ↓
        ECPay Mock
          ↓
        ATM 付款資訊

    真正串接綠界時：

        ECPayMockAdapter
              ↓
        ECPayProductionAdapter

    PaymentService 不需要修改。
    """

    def __init__(
        self,
        merchant_id: str = "2000132",
        atm_expire_minutes: int = 3 * 24 * 60,
    ):
        """
        Args:
            merchant_id:
                Mock 商店代號

            atm_expire_minutes:
                ATM 繳費期限。

                預設：
                3 天
        """

        self.merchant_id = merchant_id
        self.atm_expire_minutes = atm_expire_minutes

    # ========================================================
    # 建立 ATM
    # ========================================================

    def create_atm_payment(
        self,
        *,
        merchant_trade_no: str,
        trade_amt: Decimal,
        item_name: str,
    ) -> ECPayATMResult:

        # ----------------------------------------------------
        # 產生 Mock 綠界交易編號
        # ----------------------------------------------------

        trade_no = (
            "MOCK"
            + uuid.uuid4().hex[:16].upper()
        )

        # ----------------------------------------------------
        # 模擬銀行代碼
        #
        # 808 = 玉山銀行
        #
        # 這裡只是 Mock。
        # 正式 ECPay 不應該自己產生銀行代碼。
        # ----------------------------------------------------

        bank_code = "808"

        # ----------------------------------------------------
        # 模擬虛擬帳號
        #
        # 這裡產生固定長度的測試帳號。
        # ----------------------------------------------------

        random_number = (
            uuid.uuid4().int
            % 10_000_000_000_000
        )

        v_account = (
            f"{random_number:014d}"
        )

        # ----------------------------------------------------
        # 計算 ATM 繳費期限
        # ----------------------------------------------------

        expire_date = (
            timezone.now()
            + timedelta(
                minutes=self.atm_expire_minutes
            )
        )

        # ----------------------------------------------------
        # Mock CheckMacValue
        #
        # 正式環境應該依 ECPay 規格產生。
        #
        # 目前只是讓整個架構可以模擬
        # CheckMacValue 的存在。
        # ----------------------------------------------------

        raw_value = (
            f"{self.merchant_id}"
            f"{merchant_trade_no}"
            f"{trade_amt}"
            f"{trade_no}"
        )

        check_mac_value = hashlib.sha256(
            raw_value.encode("utf-8")
        ).hexdigest()

        # ----------------------------------------------------
        # 回傳標準化結果
        # ----------------------------------------------------

        return ECPayATMResult(
            merchant_trade_no=merchant_trade_no,
            trade_no=trade_no,
            bank_code=bank_code,
            v_account=v_account,
            expire_date=expire_date,
            status="atm_created",
            check_mac_value=check_mac_value,
        )

    # ========================================================
    # 查詢付款
    # ========================================================

    def query_payment(
        self,
        *,
        merchant_trade_no: str,
    ) -> dict:

        # ----------------------------------------------------
        # Mock 暫時固定回傳 ATM_PENDING
        #
        # 真正銀行付款流程完成後，
        # 這裡可以改成 httpx 呼叫 ECPay Mock。
        # ----------------------------------------------------

        return {
            "merchant_trade_no": merchant_trade_no,
            "status": "atm_pending",
            "rtn_code": 0,
            "rtn_msg": "尚未付款",
        }