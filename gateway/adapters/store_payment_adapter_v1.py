# ============================================================
# ECPay Mock
# gateway/adapters/store_payment_adapter.py
# ============================================================

import logging
from typing import Any, Dict

import httpx

from django.conf import settings

from util.ChkMacVal import (
    generate_check_mac_value,
)

from ..interface.store_payment_gateway import (
    StorePaymentGateway,
)


logger = logging.getLogger(__name__)


class StorePaymentAdapter(
    StorePaymentGateway
):
    """
    【新增】

    ECPay Mock → E_commerce Adapter。

    ============================================================
    責任
    ============================================================

    1. 整理 Store Callback payload
    2. 重新產生 CheckMacValue
    3. 使用 HTTPX 呼叫 E_commerce
    4. 驗證 HTTP Response
    5. 解析 JSON Response

    ============================================================
    注意
    ============================================================

    這裡的 CheckMacValue：

        Ecpay Mock
             ↓
        E_commerce

    是一筆新的 MAC。

    不沿用：

        E_commerce
             ↓
        Ecpay Mock

    的原始 CheckMacValue。
    """

    def __init__(
        self,
        timeout: float = 10.0,
    ):
        """
        【新增】

        Adapter 初始化。
        """

        try:

            self.timeout = timeout

            # ------------------------------------------------
            # 【新增】
            #
            # 不猜 Store callback path。
            #
            # 由 settings 明確提供完整 URL。
            #
            # 例如：
            #
            # ECPAY_SHOP_PAYMENT_NOTIFY_URL = (
            #     "https://xxx/api/..."
            # )
            # ------------------------------------------------

            self.notify_url = (
                getattr(
                    settings,
                    "ECPAY_SHOP_PAYMENT_NOTIFY_URL",
                    "",
                )
                or ""
            ).strip()

            if not self.notify_url:

                raise RuntimeError(
                    "ECPAY_SHOP_PAYMENT_NOTIFY_URL 未設定"
                )

        except Exception as exc:

            logger.exception(
                "StorePaymentAdapter 初始化失敗"
            )

            raise RuntimeError(
                "StorePaymentAdapter 初始化失敗"
            ) from exc

    # ========================================================
    # Ecpay Mock → E_commerce
    # ========================================================

    def notify_payment_result(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        【新增】

        把 ECPay Mock 已確認的付款結果
        傳給 E_commerce。
        """

        try:

            if not isinstance(
                payload,
                dict,
            ):
                raise ValueError(
                    "Store Callback payload 必須是 dict"
                )

            merchant_trade_no = (
                payload.get(
                    "merchant_trade_no"
                )
            )

            if not merchant_trade_no:

                raise ValueError(
                    "Store Callback 缺少 merchant_trade_no"
                )

            # ------------------------------------------------
            # 【新增】
            #
            # 重新建立 outgoing payload。
            #
            # 不直接修改呼叫端 payload。
            # ------------------------------------------------

            signed_payload = dict(
                payload
            )

            signed_payload.pop(
                "CheckMacValue",
                None,
            )

            signed_payload[
                "merchant_trade_no"
            ] = str(
                merchant_trade_no
            )

            # ------------------------------------------------
            # 【新增】
            #
            # Ecpay Mock → E_commerce
            # 的 MAC。
            # ------------------------------------------------

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
                    "ECPAY_HASH_KEY / ECPAY_HASH_IV 未設定"
                )

            signed_payload[
                "CheckMacValue"
            ] = generate_check_mac_value(
                signed_payload,
                hash_key,
                hash_iv,
            )

            logger.info(
                "開始通知 E_commerce Payment Result: "
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            # ------------------------------------------------
            # 【保留】
            #
            # HTTPX 僅在 Adapter。
            # ------------------------------------------------

            try:

                response = httpx.post(
                    self.notify_url,
                    json=signed_payload,
                    timeout=self.timeout,
                )

            except httpx.TimeoutException as exc:

                logger.exception(
                    "E_commerce Payment Callback timeout"
                )

                raise RuntimeError(
                    "E_commerce Payment Callback 逾時"
                ) from exc

            except httpx.RequestError as exc:

                logger.exception(
                    "E_commerce Payment Callback request error"
                )

                raise RuntimeError(
                    "E_commerce Payment Callback 呼叫失敗"
                ) from exc

            # ------------------------------------------------
            # 【新增】
            # HTTP 狀態驗證
            # ------------------------------------------------

            try:

                response.raise_for_status()

            except httpx.HTTPStatusError as exc:

                logger.exception(
                    "E_commerce Payment Callback HTTP error: %s",
                    response.status_code,
                )

                raise RuntimeError(
                    "E_commerce Payment Callback HTTP 回應錯誤"
                ) from exc

            # ------------------------------------------------
            # 【新增】
            # JSON 解析
            # ------------------------------------------------

            try:

                response_data = (
                    response.json()
                )

            except ValueError as exc:

                logger.exception(
                    "E_commerce Payment Callback 回傳非 JSON"
                )

                raise RuntimeError(
                    "E_commerce Payment Callback 回傳格式錯誤"
                ) from exc

            if not isinstance(
                response_data,
                dict,
            ):

                raise RuntimeError(
                    "E_commerce Payment Callback 回傳資料格式錯誤"
                )

            logger.info(
                "E_commerce Payment Callback 完成: "
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            return {
                "success": True,
                "merchant_trade_no": str(
                    merchant_trade_no
                ),
                "response_data": response_data,
            }

        except ValueError:
            raise

        except RuntimeError:
            raise

        except Exception as exc:

            logger.exception(
                "StorePaymentAdapter "
                "notify_payment_result 發生未預期錯誤"
            )

            raise RuntimeError(
                "E_commerce Payment Callback 失敗"
            ) from exc