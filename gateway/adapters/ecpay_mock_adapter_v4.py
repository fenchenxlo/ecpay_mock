# ============================================================
# commerce_shop/adapter/ecpay_mock_adapter.py
# ============================================================
#
# Adapter Layer
#
# 【本次重構】
#
# Adapter 的責任：
#
#     1. 實作 ECPayGateway Interface
#     2. 使用 HTTPX 呼叫 ECPay Mock
#     3. 產生 Store → ECPay Mock 的 CheckMacValue
#     4. 將 ECPay Mock Response
#        轉成 Gateway 可使用的格式
#
# Adapter 可以：
#
#     ✅ httpx.post()
#     ✅ CheckMacValue 計算
#
# Adapter 不負責：
#
#     ❌ Django ORM
#     ❌ Order.objects
#     ❌ Payment.objects
#     ❌ View
#     ❌ ATM 自行產生
#
# ATM 流程：
#
#     Store
#       ↓
#     ECPayMockAdapter
#       ↓ HTTPX
#     ECPay Mock
#       ↓
#     ECPayService
#       ↓
#     ECPayMockAdapter
#       ↓ HTTPX
#     Bank Mock
#       ↓
#     bank_code
#     v_account
#     expire_date
#
# ============================================================


import logging
from typing import Any, Dict

import httpx
from django.conf import settings

from util.ChkMacVal import (
    generate_check_mac_value,
)

from ..interface.ecpay_gateway import (
    ECPayGateway,
)


logger = logging.getLogger(__name__)


class ECPayMockAdapter(ECPayGateway):
    """
    ECPay Mock Adapter。

    Store 端實際進行 HTTPX 呼叫的位置。

    本 Adapter 目前負責：

        Store
          ↓
        ECPay Mock

    不負責：

        ❌ ATM 產生
        ❌ Django ORM
        ❌ Payment DB
    """

    def __init__(
        self,
        *,
        timeout: float = 10.0,
    ):
        """
        初始化 Adapter。

        timeout：
            HTTPX timeout 秒數。
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
        # 使用：
        #
        #     HF_SPACE_ECPAY_MOCK_URL
        # ====================================================

        self.base_url = (
            getattr(
                settings,
                "HF_SPACE_ECPAY_MOCK_URL",
                "",
            )
            .rstrip("/")
        )

        if not self.base_url:

            raise RuntimeError(
                "未設定 HF_SPACE_ECPAY_MOCK_URL"
            )

        # ====================================================
        # 【新增】
        #
        # 正確 ATM 建立接口：
        #
        #     /gateway/ecpay_gateway_checkout/
        #
        # 【刪除/移出】
        #
        # 舊接口：
        #
        #     /gateway/checkout/
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

        呼叫 ECPay Mock 建立 ATM。

        payload 使用 Dict，
        方便未來增加綠界欄位。

        例如：

            {
                "merchant_trade_no": "...",
                "trade_amt": "...",
                "item_name": "...",
                "choose_payment": "ATM",
                ...
            }

        本 Adapter 負責：

            payload
                ↓
            CheckMacValue
                ↓
            HTTPX
                ↓
            ECPay Mock
                ↓
            ATM Response
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
        # 取得必要欄位
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

        item_name = (
            payload.get(
                "item_name",
                "購買商品",
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

        if not item_name:

            raise ValueError(
                "item_name 不可為空"
            )

        # ====================================================
        # 【新增】
        # ATM 固定使用 ATM
        # ====================================================

        request_payload = dict(
            payload
        )

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

        request_payload[
            "item_name"
        ] = str(
            item_name
        )

        request_payload[
            "choose_payment"
        ] = "ATM"

        # ====================================================
        # 【新增】
        #
        # 原始 payload 如果帶有 CheckMacValue，
        # 不可以直接重複拿來使用。
        #
        # 必須先移除，再重新計算。
        #
        # 【注意】
        #
        # Store → ECPay Mock
        #
        # 這一次的 CheckMacValue
        # 必須由 Store Adapter 重新計算。
        # ====================================================

        request_payload.pop(
            "CheckMacValue",
            None,
        )

        # ====================================================
        # 【新增】
        #
        # CheckMacValue 計算
        #
        # 計算內容不包含：
        #
        #     CheckMacValue
        #
        # 計算完成後才加入。
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

            # 【新增】
            #
            # 計算完成後，
            # 才加入 CheckMacValue。
            #
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
        #
        # HTTPX → ECPay Mock
        #
        # 單次 Request 使用 httpx.post()。
        #
        # 如果未來同一 Adapter 需要大量重複 Request，
        # 才考慮改成 httpx.Client。
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
        # 解析 JSON
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
        # 檢查 ATM 是否建立成功
        # ====================================================

        if not data.get("status"):

            raise ValueError(
                data.get(
                    "message",
                    "ECPay Mock ATM 建立失敗",
                )
            )

        # ====================================================
        # 【新增】
        # 取得 payment
        # ====================================================

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
        # 驗證 ATM 核心欄位
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
        #
        # 確認 merchant_trade_no 沒有被外部服務改掉。
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
        # provider_transaction_id
        #
        # Store 新 Models 不使用舊的：
        #
        #     ❌ transaction_id
        #
        # 對應：
        #
        #     Payment.provider_transaction_id
        #
        # ECPay Mock 的 trade_no
        # 可以作為 provider transaction id。
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
        #
        # 回傳 Store Service 統一格式。
        #
        # 不在 Adapter 建立 Payment。
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
                payment[
                    "expire_date"
                ],

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

        查詢 ECPay Mock 付款資訊。
        """

        if not merchant_trade_no:

            raise ValueError(
                "merchant_trade_no 不可為空"
            )

        # ====================================================
        # 【保留】
        # Query URL
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
        #
        # Query Request 也簽署 CheckMacValue。
        #
        # 如果目前 ECPay Mock 的
        # payment_info View 沒有要求 MAC，
        # 可在實際測試時再同步調整。
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
                "ECPay Mock Query CheckMacValue 計算失敗"
            )

            raise RuntimeError(
                "ECPay Mock Query Request 簽章失敗"
            ) from ex

        # ====================================================
        # 【保留】
        # HTTPX Query
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
                "ECPay Mock Query Timeout"
            )

            raise RuntimeError(
                "ECPay Mock 查詢逾時"
            ) from ex

        except httpx.HTTPStatusError as ex:

            logger.exception(
                "ECPay Mock Query HTTP 錯誤：%s",
                ex.response.status_code,
            )

            raise RuntimeError(
                "ECPay Mock 查詢失敗"
            ) from ex

        except httpx.RequestError as ex:

            logger.exception(
                "ECPay Mock Query HTTPX 失敗"
            )

            raise RuntimeError(
                "ECPay Mock 查詢無法連線"
            ) from ex

        except Exception as ex:

            logger.exception(
                "ECPay Mock Query 發生未知錯誤"
            )

            raise RuntimeError(
                "ECPay Mock 查詢失敗"
            ) from ex

        # ====================================================
        # 【保留】
        # 解析 JSON
        # ====================================================

        try:

            data = response.json()

        except ValueError as ex:

            logger.exception(
                "ECPay Mock Query JSON 解析失敗"
            )

            raise RuntimeError(
                "ECPay Mock Query Response 格式錯誤"
            ) from ex

        if not isinstance(
            data,
            dict,
        ):

            raise RuntimeError(
                "ECPay Mock Query Response 必須是 Object"
            )

        return data