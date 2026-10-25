# commerce_shop/gateways/ecpay_gateway.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


# ============================================================
# ECPay ATM 建立結果
# ============================================================

@dataclass
class ECPayATMResult:
    """
    ECPay ATM 建立後回傳的標準格式。

    PaymentService 不需要知道：
        - Mock 怎麼產生銀行代碼
        - Mock 怎麼產生虛擬帳號
        - Mock 怎麼計算期限

    PaymentService 只需要使用這個結果。
    """

    merchant_trade_no: str

    trade_no: str

    bank_code: str

    v_account: str

    expire_date: datetime

    status: str

    check_mac_value: str | None = None


# ============================================================
# ECPay Gateway Interface
# ============================================================

class ECPayGateway(ABC):
    """
    綠界 Gateway Interface

    未來可以有：

        ECPayMockAdapter
                ↑
        開發 / 測試

        ECPayProductionAdapter
                ↑
        正式環境

    PaymentService 完全不需要修改。
    """

    @abstractmethod
    def create_atm_payment(
        self,
        *,
        merchant_trade_no: str,
        trade_amt: Decimal,
        item_name: str,
    ) -> ECPayATMResult:
        """
        建立 ATM 付款。

        Args:
            merchant_trade_no:
                商店訂單編號

            trade_amt:
                交易金額

            item_name:
                商品名稱

        Returns:
            ECPayATMResult
        """

        raise NotImplementedError

    @abstractmethod
    def query_payment(
        self,
        *,
        merchant_trade_no: str,
    ) -> dict:
        """
        查詢付款狀態。

        Mock / 正式 ECPay 都必須實作。

        Returns:
            dict
        """

        raise NotImplementedError