# ============================================================
# ECPay Mock
# gateway/interface/ecpay_gateway.py
# ============================================================

from abc import ABC, abstractmethod
from typing import Any, Dict


class ECPayGateway(ABC):
    """
    【修改】

    ECPay Mock Gateway Interface。

    ============================================================
    目前實際用途
    ============================================================

    在 Ecpay Mock 專案內：

        ECPayService
              ↓
        ECPayGateway
              ↓
        ECPayMockAdapter
              ↓ HTTPX
        Bank Mock

    因此這個 Interface 的實作，
    實際上負責 ECPay Mock → Bank Mock 的外部呼叫。

    ============================================================
    Gateway / Adapter 不負責
    ============================================================

    1. 不直接操作 Django ORM
    2. 不建立 PaymentRequest
    3. 不建立 PaymentNotification
    4. 不產生 ECPay trade_no
    5. 不產生 bank_code
    6. 不產生 v_account
    7. 不產生 expire_date
    8. 不負責商業流程
    9. 不由 View 直接呼叫 HTTPX

    ============================================================
    資料來源
    ============================================================

    Bank Mock 負責提供：

        bank_code
        v_account
        expire_date
        payment_status

    ECPayService 再根據結果建立自己的 trade_no。
    """

    @abstractmethod
    def create_atm_payment(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        【修改】

        請求 Bank Mock 建立 ATM 虛擬帳號。

        預期回傳：

            {
                "success": True,
                "merchant_trade_no": "...",
                "bank_code": "...",
                "v_account": "...",
                "expire_date": "...",
                "payment_status": "...",
                "response_data": {...},
            }

        注意：

        provider_transaction_id / trade_no
        不由 Adapter 產生。
        """

        raise NotImplementedError

    # 【新增】取消 ATM 虛擬帳號（ECPay Mock → Bank Mock）
    @abstractmethod
    def cancel_account(
        self,
        merchant_trade_no: str,
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def query_payment(
        self,
        merchant_trade_no: str,
    ) -> Dict[str, Any]:
        """
        【保留】

        查詢 Bank / Payment 狀態。

        實際查詢方式由 Adapter 實作。
        """

        raise NotImplementedError