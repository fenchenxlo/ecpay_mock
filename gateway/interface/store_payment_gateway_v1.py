# ============================================================
# ECPay Mock
# gateway/interface/store_payment_gateway.py
# ============================================================

from abc import ABC, abstractmethod
from typing import Any, Dict


class StorePaymentGateway(ABC):
    """
    【新增】

    ECPay Mock → E_commerce Payment Callback Gateway Interface。

    ============================================================
    責任
    ============================================================

    定義 Ecpay Mock 如何把付款結果通知 Store。

    正式流程：

        Ecpay Mock
             ↓
        StorePaymentGateway
             ↓
        StorePaymentAdapter
             ↓ HTTPX
        E_commerce

    ============================================================
    禁止
    ============================================================

    1. 不使用 Django ORM
    2. 不使用 httpx
    3. 不處理 PaymentRequest
    4. 不處理 PaymentNotification
    5. 不產生 ATM
    6. 不計算付款商業邏輯

    Adapter 才負責 HTTPX 與 CheckMacValue 重新簽章。
    """

    @abstractmethod
    def notify_payment_result(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        【新增】

        將 ECPay Mock 已確認的付款結果通知
        E_commerce。

        payload 是「已整理完成」的 callback 資料。

        Adapter 負責：

            payload
                ↓
            CheckMacValue
                ↓
            HTTPX
                ↓
            E_commerce
        """

        raise NotImplementedError