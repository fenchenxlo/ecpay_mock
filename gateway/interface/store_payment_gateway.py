# ============================================================
# Ecpay_mock
# interface/store_payment_gateway.py
# ============================================================

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict


# ============================================================
# 【新增】
# Ecpay Mock → E_commerce
# Store Payment Callback Result
# ============================================================

@dataclass
class StorePaymentNotifyResult:
    """
    【新增】

    Ecpay Mock 將付款結果通知 E_commerce 後，
    Adapter 回傳給 Service 的業務結果。

    Interface 層只描述資料結果，
    不直接暴露 httpx.Response。
    """

    success: bool
    status_code: int
    message: str
    response_data: Dict[str, Any]


# ============================================================
# 【新增】
# StorePaymentGateway
# ============================================================

class StorePaymentGateway(ABC):
    """
    【新增】

    Ecpay Mock → E_commerce 的付款通知 Gateway Interface。

    ========================================================
    責任
    ========================================================

    1. 定義「通知 E_commerce」的介面。
    2. 讓 ECPayService 不需要知道 HTTPX。
    3. 讓 ECPayService 不需要知道實際 callback URL。
    4. 讓 Adapter 負責真正的 HTTP 通訊。

    ========================================================
    不負責
    ========================================================

    ❌ Django ORM
    ❌ PaymentRequest 寫入
    ❌ PaymentNotification 寫入
    ❌ Order / Payment business logic
    ❌ httpx.post()
    ❌ CheckMacValue 實際計算
    ❌ ATM 產生

    ========================================================
    Architecture
    ========================================================

    ECPayService
        ↓
    StorePaymentGateway
        ↓
    StorePaymentAdapter
        ↓
    HTTPX
        ↓
    E_commerce /payment_callback/
    """

    @abstractmethod
    def notify_payment_result(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        【新增】

        將付款結果通知 E_commerce。

        Parameters
        ----------
        payload:
            Ecpay Mock 已完成付款處理後，
            準備送給 E_commerce 的 callback payload。

        Returns
        -------
        StorePaymentNotifyResult
            E_commerce callback 的處理結果。
        """

        raise NotImplementedError