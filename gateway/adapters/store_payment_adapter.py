# ============================================================
# Ecpay_mock
# adapters/store_payment_adapter.py
# ============================================================

import logging
from typing import Any, Dict

import httpx
from django.conf import settings

from ..interface.store_payment_gateway import (
    StorePaymentGateway,
    StorePaymentNotifyResult,
)

# ============================================================
# 【保留】
# 沿用 Ecpay Mock 目前既有的 CheckMacValue 計算工具。
#
# 注意：
# 這裡不要另外複製一套 ECPay MAC 演算法，
# 必須和目前 Ecpay Mock 已使用的 MAC helper 保持一致。
# ============================================================

# from util import (
    # generate_check_mac_value,
# )
from util.ChkMacVal import generate_check_mac_value

logger = logging.getLogger(__name__)


# ============================================================
# 【新增】
# StorePaymentAdapter
# ============================================================

class StorePaymentAdapter(StorePaymentGateway):
    """
    【新增】

    Ecpay Mock → E_commerce 的 Callback Adapter。

    ========================================================
    Adapter 責任
    ========================================================

    1. 準備給 E_commerce 的 callback payload。
    2. 加入 CheckMacValue。
    3. 使用 HTTPX POST 到 E_commerce。
    4. 處理 HTTPX transport error。
    5. 將 E_commerce response 轉成
       StorePaymentNotifyResult。

    ========================================================
    不負責
    ========================================================

    ❌ Django ORM
    ❌ PaymentRequest business logic
    ❌ PaymentNotification business logic
    ❌ Order 狀態判斷
    ❌ Payment 狀態判斷
    ❌ ATM 產生
    ❌ Bank Mock 呼叫

    ========================================================
    Architecture
    ========================================================

    ECPayService
        ↓
    StorePaymentGateway
        ↓
    StorePaymentAdapter
        │
        ├── CheckMacValue
        │
        └── HTTPX
              ↓
        E_commerce /payment_callback/
    """

    # ========================================================
    # 【新增】
    # 建構 Adapter
    # ========================================================

    def __init__(
        self,
        callback_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        """
        【新增】

        Parameters
        ----------
        callback_url:
            可由 Service / 測試環境直接注入。
            未提供時，從 Django settings 取得。

        timeout:
            HTTPX timeout。
            未提供時使用 settings 或預設值。
        """

        self.callback_url = (
            callback_url
            or self._get_callback_url()
        )

        self.timeout = (
            timeout
            if timeout is not None
            else getattr(
                settings,
                "STORE_PAYMENT_CALLBACK_TIMEOUT",
                10.0,
            )
        )

    # ========================================================
    # 【新增】
    # 取得 E_commerce Callback URL
    # ========================================================

    @staticmethod
    def _get_callback_url() -> str:
        """
        【修改】

        Ecpay Mock → E_commerce ATM Payment callback URL。

        優先使用：
            STORE_PAYMENT_CALLBACK_URL

        若沒有設定，則使用：
            HF_SPACE_E_COMMERCE_URL
            + /commerce_shop/atm_payment_notify/

        --------------------------------------------------------
        注意
        --------------------------------------------------------
        不使用 Ecpay Mock 自己的 BACKEND_URL，
        因為這裡的目標是 E_commerce。
        """

        configured_url = getattr(
            settings,
            "STORE_PAYMENT_CALLBACK_URL",
            "",
        )

        if configured_url:
            return configured_url.rstrip("/")

        ecommerce_url = getattr(
            settings,
            "HF_SPACE_E_COMMERCE_URL",
            "",
        )

        if not ecommerce_url:
            raise RuntimeError(
                "缺少 STORE_PAYMENT_CALLBACK_URL 或 "
                "HF_SPACE_E_COMMERCE_URL"
            )

        return (
            ecommerce_url.rstrip("/")
            + "/commerce_shop/atm_payment_notify/"
        )

    # ========================================================
    # 【新增】
    # 建立給 E_commerce 的 Callback Payload
    # ========================================================

    @staticmethod
    def _build_callback_payload(
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        【新增】

        建立實際送給 E_commerce 的資料。

        非常重要：

        1. 不直接修改 Service 傳進來的 payload。
        2. 移除既有 CheckMacValue。
        3. 重新依目前資料產生 CheckMacValue。
        4. 最後才把 CheckMacValue 放回 payload。

        這樣可以避免重複使用舊 MAC。
        """

        if not isinstance(payload, dict):
            raise ValueError(
                "Store callback payload 必須是 dict"
            )

        callback_payload = dict(payload)

        # ----------------------------------------------------
        # 【新增】
        # 移除舊 CheckMacValue
        # ----------------------------------------------------

        callback_payload.pop(
            "CheckMacValue",
            None,
        )

        callback_payload.pop(
            "check_mac_value",
            None,
        )

        # ----------------------------------------------------
        # 【新增】
        # 產生新的 CheckMacValue
        # ----------------------------------------------------

        check_mac_value = generate_check_mac_value(
            callback_payload,
            settings.ECPAY_HASH_KEY,
            settings.ECPAY_HASH_IV,
        )

        # ----------------------------------------------------
        # 【新增】
        # 將新的 MAC 加入 outbound payload
        # ----------------------------------------------------

        callback_payload[
            "CheckMacValue"
        ] = check_mac_value

        return callback_payload

    # ========================================================
    # 【新增】
    # Notify E_commerce
    # ========================================================

    def notify_payment_result(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        【新增】

        Ecpay Mock → E_commerce ATM Payment Callback。

        HTTPX 只允許存在 Adapter，
        所以真正的 POST 由本方法執行。
        """

        # ====================================================
        # 【新增】
        # Callback URL validation
        # ====================================================

        if not self.callback_url:
            raise RuntimeError(
                "E_commerce payment callback URL 未設定"
            )

        # ====================================================
        # 【新增】
        # 建立並簽署 outbound payload
        # ====================================================

        callback_payload = (
            self._build_callback_payload(
                payload
            )
        )

        logger.info(
            "Ecpay Mock → E_commerce payment callback: %s",
            self.callback_url,
        )

        # ====================================================
        # 【新增】
        # HTTPX
        #
        # 只有 Adapter 可以使用 HTTPX。
        # ====================================================

        try:
            response = httpx.post(
                self.callback_url,
                json=callback_payload,
                headers={
                    "Content-Type": (
                        "application/json"
                    ),
                },
                timeout=self.timeout,
            )

        except httpx.RequestError as exc:

            logger.exception(
                "Ecpay Mock → E_commerce callback HTTPX 失敗"
            )

            return {
                "success": False,
                "status_code": 0,
                "message": "E_commerce callback HTTPX request failed",
                "response_data": {
                    "error": str(exc),
                },
            }


            # return StorePaymentNotifyResult(
                # success=False,
                # status_code=0,
                # message=(
                    # "E_commerce callback HTTPX request failed"
                # ),
                # response_data={
                    # "error": str(exc),
                # },
            # )

        # ====================================================
        # 【新增】
        # 解析 E_commerce response
        # ====================================================

        try:
            response_data = response.json()

            if not isinstance(
                response_data,
                dict,
            ):
                response_data = {
                    "raw_response": response_data,
                }

        except ValueError:

            response_data = {
                "raw_response": response.text,
            }

        # ====================================================
        # 【新增】
        # HTTP Status 判斷
        # ====================================================

        success = (
            200 <= response.status_code < 300
        )

        if success:

            message = (
                str(
                    response_data.get(
                        "message",
                        "E_commerce callback success",
                    )
                )
            )

        else:

            message = (
                str(
                    response_data.get(
                        "message",
                        "E_commerce callback failed",
                    )
                )
            )
        
        return {
            "success": success,
            "status_code": response.status_code,
            "message": message,
            "response_data": response_data,
        }
        

        # # ====================================================
        # # 【新增】
        # # 統一回傳 Gateway Result
        # # ====================================================

        # return StorePaymentNotifyResult(
            # success=success,
            # status_code=response.status_code,
            # message=message,
            # response_data=response_data,
        # )