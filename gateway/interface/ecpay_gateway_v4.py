# ============================================================
# ECPay Mock
# gateway/interface/ecpay_gateway.py
# ============================================================
#
# Gateway Interface
#
# 【本次修改】
#
# ECPayService
#       ↓
# ECPayGateway
#       ↓
# ECPayMockAdapter
#
# Interface 只定義契約。
#
# 不負責：
#
#     ❌ Django ORM
#     ❌ httpx
#     ❌ CheckMacValue 計算
#     ❌ CheckMacValue 驗證
#     ❌ 產生 ATM
#
# ============================================================

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


# ============================================================
# ATM Result
# ============================================================

@dataclass
class ECPayATMResult:
    """
    【修改】

    ECPay Gateway 統一 ATM 回傳格式。

    ATM 建立流程：

        Bank Mock
            ↓
        bank_code
        v_account
        expire_date
            ↓
        ECPayMockAdapter
            ↓
        ECPayService
            ↓
        trade_no

    TradeNo 不由 Bank Mock 產生。
    """

    # ========================================================
    # 【保留】
    # Store 提供的商店交易編號
    # ========================================================

    merchant_trade_no: str

    # ========================================================
    # 【保留】
    # Bank Mock 產生
    # ========================================================

    bank_code: str

    # ========================================================
    # 【保留】
    # Bank Mock 產生
    # ========================================================

    v_account: str

    # ========================================================
    # 【保留】
    # Bank Mock 產生
    # ========================================================

    expire_date: datetime

    # ========================================================
    # 【保留】
    # ATM 狀態
    # ========================================================

    status: str

    # ========================================================
    # 【修改】
    #
    # TradeNo：
    #
    #     Bank Mock 回來時尚未產生
    #     → None
    #
    #     ECPayService 後續產生
    #     → 字串
    #
    # ========================================================

    trade_no: Optional[str] = None

    # ========================================================
    # 【修改】
    #
    # CheckMacValue 可以沒有。
    # ========================================================

    check_mac_value: Optional[str] = None


# ============================================================
# ECPay Gateway
# ============================================================

class ECPayGateway(ABC):
    """
    ECPay Gateway Interface。

    【修改】

    ECPayService 只依賴這個 Interface。

    真正實作：

        ECPayMockAdapter

    未來可以替換：

        ECPayProductionAdapter
    """

    # ========================================================
    # 建立 ATM
    # ========================================================

    @abstractmethod
    def create_atm_payment(
        self,
        payload: Dict[str, Any],
    ) -> ECPayATMResult:
        """
        【修改】

        建立 ATM 付款資訊。

        payload 使用 Dict。

        例如：

            {
                "merchant_trade_no": "...",
                "merchant_trade_date": "...",
                "trade_amt": "...",
                "trade_desc": "...",
                "item_name": "...",
                "payment_type": "aio",
                "choose_payment": "ATM",
                ...
            }

        Interface 不負責：

            ❌ CheckMacValue
            ❌ HashKey
            ❌ HashIV
            ❌ HTTPX
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