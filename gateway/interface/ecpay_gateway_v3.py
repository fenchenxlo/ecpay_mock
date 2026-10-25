# ============================================================
# commerce_shop/interfaces/ecpay_gateway.py
# ============================================================

from abc import ABC, abstractmethod
from typing import Any, Dict


class ECPayGateway(ABC):
    """
    ECPay Gateway Interface。

    【修改】

    使用 Dict payload。

    方便未來增加更多 ECPay 欄位。

    Interface 不負責：

        ❌ httpx
        ❌ CheckMacValue
        ❌ HashKey / HashIV
        ❌ ECPay URL
    """

    # ========================================================
    # 建立 ATM
    # ========================================================

    @abstractmethod
    def create_atm_payment(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        【修改】

        建立 ATM 付款資訊。

        payload 可以包含：

            merchant_trade_no
            merchant_trade_date
            trade_amt
            trade_desc
            item_name
            payment_type
            choose_payment
            ...
        """

        raise NotImplementedError

    # ========================================================
    # 查詢付款
    # ========================================================

    @abstractmethod
    def query_payment(
        self,
        merchant_trade_no: str,
    ) -> Dict[str, Any]:
        """
        【保留】

        查詢付款狀態。
        """

        raise NotImplementedError