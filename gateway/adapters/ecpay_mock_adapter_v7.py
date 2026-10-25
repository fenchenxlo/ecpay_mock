# ============================================================
# gateway/adapters/ecpay_mock_adapter.py
# ============================================================
#
# Adapter Layer
#
# 【本次修改】
#
# Store → ECPay Mock
#
# Adapter 負責：
#
#     1. 實作 ECPayGateway
#     2. 建立 ECPay Request payload
#     3. 產生 CheckMacValue
#     4. HTTPX 呼叫 ECPay Mock
#     5. 解析 ECPay Mock Response
#
# Adapter 不負責：
#
#     ❌ Django ORM
#     ❌ Order
#     ❌ Payment
#     ❌ 產生 ATM
#     ❌ 產生 TradeNo
#
# ============================================================

import logging
from typing import Any, Dict

import httpx
from django.conf import settings

from util.ChkMacVal import (
    generate_check_mac_value,
)

from ..interfaces.ecpay_gateway import (
    ECPayGateway,
)


logger = logging.getLogger(__name__)


class ECPayMockAdapter(ECPayGateway):
    """
    Store → ECPay Mock Adapter。

    ATM 流程：

        Store Service
              ↓
        ECPayGateway
              ↓
        ECPayMockAdapter
              ↓
        CheckMacValue
              ↓ HTTPX
        ECPay Mock
    """

    def __init__(
        self,
        *,
        timeout: float = 10.0,
    ):
        """
        初始化 Adapter。
        """

        # ====================================================
        # 【保留】
        # HTTPX timeout
        # ====================================================

        self.timeout = timeout

        # ====================================================
        # 【修改】
        #
        # Store → ECPay Mock
        #
        # 使用 ECPay Mock Base URL。
        # ====================================================

        self.base_url = (
            getattr(
                settings,
                "HF_SPACE_ECPAY_MOCK_URL",
                "",
            )
            or ""
        ).rstrip("/")

        if not self.base_url:

            raise RuntimeError(
                "未設定 HF_SPACE_ECPAY_MOCK_URL"
            )

        # ====================================================
        # 【新增】
        #
        # 正確 ATM 接口：
        #
        #     /gateway/ecpay_gateway_checkout/
        # ====================================================

        self.atm_url = (
            f"{self.base_url}"
            f"/gateway/ecpay_gateway_checkout/"
        )

    # ========================================================
    # 建立 ATM
    # ========================================================

    def create_atm_payment(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        【修改】

        Store → ECPay Mock。

        使用 Dict payload，
        方便未來對接更多 ECPay 欄位。
        """

        # ====================================================
        # 【新增】
        # payload 型別驗證
        # ====================================================

        if not isinstance(
            payload,
            dict,
        ):

            raise ValueError(
                "payload 必須是 Object"
            )

        # ====================================================
        # 【新增】
        # 必要欄位驗證
        # ====================================================

        merchant_trade_no = (
            payload.get(
                "merchant_trade_no"
            )
        )

        trade_amt = (
            payload.get(
                "trade_amt"
            )
        )

        if not merchant_trade_no:

            raise ValueError(
                "缺少 merchant_trade_no"
            )

        if trade_amt in (
            None,
            "",
        ):

            raise ValueError(
                "缺少 trade_amt"
            )

        # ====================================================
        # 【新增】
        #
        # 建立 Request payload。
        #
        # 不直接修改呼叫端的 dict。
        # ====================================================

        request_payload = dict(
            payload
        )

        # ====================================================
        # 【新增】
        # 格式統一
        # ====================================================

        request_payload[
            "merchant_trade_no"
        ] = str(
            merchant_trade_no
        )

        request_payload[
            "trade_amt"
        ] = str(
            trade_amt
        )

        request_payload.setdefault(
            "item_name",
            "購買商品",
        )

        request_payload[
            "choose_payment"
        ] = "ATM"

        # ====================================================
        # 【修改】
        #
        # 先移除舊 CheckMacValue。
        #
        # Adapter 是新的 HTTP 發送邊界，
        # 必須重新計算 MAC。
        # ====================================================

        request_payload.pop(
            "CheckMacValue",
            None,
        )

        # ====================================================
        # 【新增】
        #
        # Store → ECPay Mock
        # CheckMacValue。
        #
        # 計算時：
        #
        #     不包含 CheckMacValue
        #
        # 計算完成：
        #
        #     才加入 CheckMacValue
        # ====================================================

        try:

            hash_key = getattr(
                settings,
                "ECPAY_HASH_KEY",
                "",
            )

            hash_iv = getattr(
                settings,
                "ECPAY_HASH_IV",
                "",
            )

            if not hash_key:

                raise RuntimeError(
                    "未設定 ECPAY_HASH_KEY"
                )

            if not hash_iv:

                raise RuntimeError(
                    "未設定 ECPAY_HASH_IV"
                )

            check_mac_value = (
                generate_check_mac_value(
                    request_payload,
                    hash_key,
                    hash_iv,
                )
            )

            signed_payload = {
                **request_payload,
                "CheckMacValue":
                    check_mac_value,
            }

        except Exception as ex:

            logger.exception(
                "ECPay Mock CheckMacValue 計算失敗"
            )

            raise RuntimeError(
                "ECPay Mock Request 簽章失敗"
            ) from ex

        # ====================================================
        # 【新增】
        # HTTPX → ECPay Mock
        # ====================================================

        try:

            response = httpx.post(
                self.atm_url,
                json=signed_payload,
                timeout=self.timeout,
            )

            response.raise_for_status()

        except httpx.TimeoutException as ex:

            logger.exception(
                "ECPay Mock ATM Request Timeout"
            )

            raise RuntimeError(
                "ECPay Mock 連線逾時"
            ) from ex

        except httpx.HTTPStatusError as ex:

            logger.exception(
                "ECPay Mock HTTP 錯誤：%s",
                ex.response.status_code,
            )

            raise RuntimeError(
                "ECPay Mock HTTP Request 失敗"
            ) from ex

        except httpx.RequestError as ex:

            logger.exception(
                "ECPay Mock HTTPX Request 失敗"
            )

            raise RuntimeError(
                "ECPay Mock 無法連線"
            ) from ex

        except Exception as ex:

            logger.exception(
                "ECPay Mock Adapter HTTPX 發生未知錯誤"
            )

            raise RuntimeError(
                "ECPay Mock Adapter HTTP Request 失敗"
            ) from ex

        # ====================================================
        # 【新增】
        # JSON Response
        # ====================================================

        try:

            data = response.json()

        except ValueError as ex:

            logger.exception(
                "ECPay Mock Response JSON 解析失敗"
            )

            raise RuntimeError(
                "ECPay Mock Response 格式錯誤"
            ) from ex

        if not isinstance(
            data,
            dict,
        ):

            raise RuntimeError(
                "ECPay Mock Response 必須是 Object"
            )

        # ====================================================
        # 【新增】
        # ATM 建立成功驗證
        # ====================================================

        if not data.get(
            "status"
        ):

            raise ValueError(
                data.get(
                    "message",
                    "ECPay Mock ATM 建立失敗",
                )
            )

        payment = data.get(
            "payment"
        )

        if not isinstance(
            payment,
            dict,
        ):

            raise RuntimeError(
                "ECPay Mock 缺少 payment 資料"
            )

        # ====================================================
        # 【新增】
        # ATM Response 必要欄位
        # ====================================================

        required_fields = [
            "merchant_trade_no",
            "trade_no",
            "bank_code",
            "v_account",
            "expire_date",
            "status",
        ]

        missing_fields = [
            field
            for field in required_fields
            if payment.get(field)
            in (
                None,
                "",
            )
        ]

        if missing_fields:

            raise RuntimeError(
                "ECPay Mock ATM Response 缺少欄位："
                + ", ".join(
                    missing_fields
                )
            )

        # ====================================================
        # 【新增】
        # MerchantTradeNo 一致性驗證
        # ====================================================

        if (
            str(
                payment[
                    "merchant_trade_no"
                ]
            )
            != str(
                merchant_trade_no
            )
        ):

            logger.error(
                "ECPay Mock merchant_trade_no 不一致："
                "expected=%s, actual=%s",
                merchant_trade_no,
                payment[
                    "merchant_trade_no"
                ],
            )

            raise RuntimeError(
                "ECPay Mock 回傳訂單編號不一致"
            )

        # ====================================================
        # 【新增】
        #
        # Provider Transaction ID
        #
        # Store 新 Model 使用：
        #
        #     provider_transaction_id
        #
        # 不使用舊：
        #
        #     transaction_id
        # ====================================================

        provider_transaction_id = (
            payment.get(
                "provider_transaction_id"
            )
            or payment.get(
                "trade_no"
            )
        )

        if not provider_transaction_id:

            raise RuntimeError(
                "ECPay Mock 未回傳 provider_transaction_id"
            )

        # ====================================================
        # 【新增】
        # expire_date 基本驗證
        # ====================================================

        expire_date = payment.get(
            "expire_date"
        )

        if not expire_date:

            raise RuntimeError(
                "ECPay Mock 缺少 expire_date"
            )

        # ====================================================
        # 【新增】
        #
        # Response 統一格式。
        # ====================================================

        return {

            "success":
                True,

            "provider_transaction_id":
                str(
                    provider_transaction_id
                ),

            "bank_code":
                str(
                    payment[
                        "bank_code"
                    ]
                ),

            "v_account":
                str(
                    payment[
                        "v_account"
                    ]
                ),

            "expire_date":
                expire_date,

            "response_data":
                data,
        }

    # ========================================================
    # 查詢付款
    # ========================================================

    def query_payment(
        self,
        merchant_trade_no: str,
    ) -> Dict[str, Any]:
        """
        【保留】

        查詢付款狀態。
        """

        if not merchant_trade_no:

            raise ValueError(
                "merchant_trade_no 不可為空"
            )

        # ====================================================
        # 【新增】
        #
        # Query 使用 ECPay Mock，
        # 不是 Bank Mock。
        # ====================================================

        url = (
            f"{self.base_url}"
            f"/gateway/payment_info/"
        )

        payload = {
            "merchant_trade_no":
                str(
                    merchant_trade_no
                ),
        }

        # ====================================================
        # 【新增】
        # Query CheckMacValue
        # ====================================================

        try:

            hash_key = getattr(
                settings,
                "ECPAY_HASH_KEY",
                "",
            )

            hash_iv = getattr(
                settings,
                "ECPAY_HASH_IV",
                "",
            )

            if not hash_key or not hash_iv:

                raise RuntimeError(
                    "未設定 ECPAY_HASH_KEY / ECPAY_HASH_IV"
                )

            check_mac_value = (
                generate_check_mac_value(
                    payload,
                    hash_key,
                    hash_iv,
                )
            )

            signed_payload = {
                **payload,
                "CheckMacValue":
                    check_mac_value,
            }

        except Exception as ex:

            logger.exception(
                "ECPay Query CheckMacValue 產生失敗"
            )

            raise RuntimeError(
                "ECPay Query Request 簽章失敗"
            ) from ex

        # ====================================================
        # 【保留】
        # HTTPX
        # ====================================================

        try:

            response = httpx.post(
                url,
                json=signed_payload,
                timeout=self.timeout,
            )

            response.raise_for_status()

        except httpx.TimeoutException as ex:

            logger.exception(
                "ECPay Query Timeout"
            )

            raise RuntimeError(
                "ECPay 查詢逾時"
            ) from ex

        except httpx.HTTPStatusError as ex:

            logger.exception(
                "ECPay Query HTTP 錯誤：%s",
                ex.response.status_code,
            )

            raise RuntimeError(
                "ECPay 查詢失敗"
            ) from ex

        except httpx.RequestError as ex:

            logger.exception(
                "ECPay Query HTTPX 失敗"
            )

            raise RuntimeError(
                "ECPay 查詢無法連線"
            ) from ex

        except Exception as ex:

            logger.exception(
                "ECPay Query 發生未知錯誤"
            )

            raise RuntimeError(
                "ECPay 查詢失敗"
            ) from ex

        # ====================================================
        # 【保留】
        # JSON
        # ====================================================

        try:

            data = response.json()

        except ValueError as ex:

            logger.exception(
                "ECPay Query JSON 解析失敗"
            )

            raise RuntimeError(
                "ECPay Query Response 格式錯誤"
            ) from ex

        if not isinstance(
            data,
            dict,
        ):

            raise RuntimeError(
                "ECPay Query Response 必須是 Object"
            )

        return data