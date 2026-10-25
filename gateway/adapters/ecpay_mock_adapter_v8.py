# ============================================================
# ECPay Mock
# gateway/adapters/ecpay_mock_adapter.py
# ============================================================

import logging
from typing import Any, Dict

import httpx

from django.conf import settings

from util.ChkMacVal import generate_check_mac_value

from ..interface.ecpay_gateway import (
    ECPayGateway,
)


logger = logging.getLogger(__name__)


class ECPayMockAdapter(ECPayGateway):
    """
    【修改】

    ECPay Mock → Bank Mock Adapter。

    ============================================================
    真正責任
    ============================================================

    Ecpay Mock 收到 E_commerce 的 ATM 建立要求後：

        ECPayService
              ↓
        ECPayMockAdapter
              ↓ HTTPX
        Bank Mock
              ↓
        bank_code
        v_account
        expire_date
        payment_status

    ============================================================
    禁止
    ============================================================

    1. 不使用 Django ORM
    2. 不建立 PaymentRequest
    3. 不建立 PaymentNotification
    4. 不修改 Ecpay Mock DB
    5. 不產生虛擬帳號
    6. 不產生 bank_code
    7. 不產生 expire_date
    8. 不產生 ECPay trade_no
    """

    def __init__(self, timeout: float = 10.0):
        """
        【修改】

        Adapter 初始化。

        注意：

        這裡使用的是：

            HF_SPACE_BANK_SITE_URL

        而不是：

            HF_SPACE_ECPAY_MOCK_URL

        因為本 Adapter 的下一站是 Bank Mock。
        """

        try:
            self.timeout = timeout

            # ------------------------------------------------
            # 【修改】
            #
            # Ecpay Mock → Bank Mock
            #
            # 不是：
            # Ecpay Mock → 自己
            # ------------------------------------------------

            self.base_url = (
                getattr(
                    settings,
                    "HF_SPACE_BANK_SITE_URL",
                    "",
                )
                or ""
            ).rstrip("/")

            if not self.base_url:
                raise RuntimeError(
                    "HF_SPACE_BANK_SITE_URL 未設定"
                )

            # ------------------------------------------------
            # 【新增】
            #
            # Bank Mock 建立 ATM Virtual Account 的入口。
            #
            # Bank_Mock：
            #     /notify/create_account/
            # ------------------------------------------------

            self.create_account_url = (
                f"{self.base_url}"
                "/notify/create_account/"
            )

            # ------------------------------------------------
            # 【保留】
            #
            # Payment Query 如果之後有獨立的
            # Bank Mock Query endpoint，
            # 再接到這裡。
            #
            # 目前不能假設 Bank Mock 有：
            # /gateway/payment_info/
            # ------------------------------------------------

        except Exception as exc:

            logger.exception(
                "ECPayMockAdapter 初始化失敗"
            )

            raise RuntimeError(
                "ECPayMockAdapter 初始化失敗"
            ) from exc

    # ========================================================
    # ATM 建立
    # ========================================================

    def create_atm_payment(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        【修改】

        Ecpay Mock → Bank Mock：

            1. 驗證 payload
            2. 整理 Bank Mock request
            3. 產生 CheckMacValue
            4. HTTPX POST
            5. 驗證 HTTP Response
            6. 驗證 Bank Mock JSON
            7. 回傳 ATM 資訊

        本方法不產生 ATM 帳號。
        ATM 帳號由 Bank Mock 產生。
        """

        try:
            # ------------------------------------------------
            # 【新增】
            # 基本 payload 驗證
            # ------------------------------------------------

            if not isinstance(
                payload,
                dict,
            ):
                raise ValueError(
                    "ATM payload 必須是 dict"
                )

            merchant_trade_no = payload.get(
                "merchant_trade_no"
            )

            trade_amt = payload.get(
                "trade_amt"
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

            # ------------------------------------------------
            # 【新增】
            #
            # Bank Mock 只需要 ATM 建立所需資料。
            #
            # 不把 Store 原始 CheckMacValue
            # 直接傳下去當新的 MAC。
            # ------------------------------------------------

            bank_payload = {
                "merchant_trade_no": str(
                    merchant_trade_no
                ),
                "trade_amt": str(
                    trade_amt
                ),
                "item_name": str(
                    payload.get(
                        "item_name",
                        "購買商品",
                    )
                ),
                "choose_payment": "ATM",
            }

            # ------------------------------------------------
            # 【保留】
            #
            # 如果未來 Bank Mock 需要更多欄位，
            # 可在這裡明確增加。
            #
            # 目前不把整個 payload 無差別傳給 Bank Mock，
            # 避免把 ECPay 專用欄位全部外洩到下一層。
            # ------------------------------------------------

            # ------------------------------------------------
            # 【新增】
            #
            # Ecpay Mock → Bank Mock 的 CheckMacValue
            #
            # Bank Mock Adapter 會驗證這一筆 MAC。
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

            bank_payload[
                "CheckMacValue"
            ] = generate_check_mac_value(
                bank_payload,
                hash_key,
                hash_iv,
            )

            logger.info(
                "Ecpay Mock 開始呼叫 Bank Mock ATM API: "
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            # ------------------------------------------------
            # 【保留】
            #
            # HTTPX 僅存在 Adapter。
            # ------------------------------------------------

            try:
                response = httpx.post(
                    self.create_account_url,
                    json=bank_payload,
                    timeout=self.timeout,
                )

            except httpx.TimeoutException as exc:

                logger.exception(
                    "Bank Mock ATM API timeout"
                )

                raise RuntimeError(
                    "Bank Mock ATM API 逾時"
                ) from exc

            except httpx.RequestError as exc:

                logger.exception(
                    "Bank Mock ATM API request error"
                )

                raise RuntimeError(
                    "Bank Mock ATM API 呼叫失敗"
                ) from exc

            # ------------------------------------------------
            # 【保留】
            # HTTP status 驗證
            # ------------------------------------------------

            try:
                response.raise_for_status()

            except httpx.HTTPStatusError as exc:

                logger.exception(
                    "Bank Mock ATM API HTTP status error: %s",
                    response.status_code,
                )

                raise RuntimeError(
                    "Bank Mock ATM API 回應錯誤"
                ) from exc

            # ------------------------------------------------
            # 【保留】
            # JSON parsing
            # ------------------------------------------------

            try:
                data = response.json()

            except ValueError as exc:

                logger.exception(
                    "Bank Mock ATM API 回傳非 JSON"
                )

                raise RuntimeError(
                    "Bank Mock ATM API 回傳格式錯誤"
                ) from exc

            if not isinstance(
                data,
                dict,
            ):
                raise RuntimeError(
                    "Bank Mock ATM API 回傳資料必須是 dict"
                )

            # ------------------------------------------------
            # 【修改】
            #
            # Bank Mock 的成功結果。
            #
            # 目前依你前面提供的 Bank_Mock Adapter，
            # 預期資料會包含：
            #
            #   status
            #   merchant_trade_no
            #   bank_code
            #   v_account
            #   trade_amt
            #   expire_date
            #   payment_status
            # ------------------------------------------------

            if not data.get("status"):

                raise ValueError(
                    data.get(
                        "message",
                        "Bank Mock ATM 建立失敗",
                    )
                )

            # ------------------------------------------------
            # 【新增】
            #
            # 支援 Bank Mock 若外層包一層 payment，
            # 但不強迫 Bank Mock 改格式。
            # ------------------------------------------------

            payment_data = data.get(
                "payment"
            )

            if isinstance(
                payment_data,
                dict,
            ):
                result_data = payment_data

            else:
                result_data = data

            # ------------------------------------------------
            # 【新增】
            # 驗證 merchant_trade_no
            # ------------------------------------------------

            response_merchant_trade_no = (
                result_data.get(
                    "merchant_trade_no"
                )
            )

            if not response_merchant_trade_no:
                raise RuntimeError(
                    "Bank Mock 回應缺少 merchant_trade_no"
                )

            if (
                str(response_merchant_trade_no)
                != str(merchant_trade_no)
            ):
                raise RuntimeError(
                    "Bank Mock merchant_trade_no 不一致"
                )

            # ------------------------------------------------
            # 【新增】
            # 驗證 Bank Mock 真正產生的 ATM 資訊
            # ------------------------------------------------

            bank_code = result_data.get(
                "bank_code"
            )

            v_account = result_data.get(
                "v_account"
            )

            expire_date = result_data.get(
                "expire_date"
            )

            payment_status = (
                result_data.get(
                    "payment_status"
                )
                or result_data.get(
                    "status"
                )
            )

            if not bank_code:
                raise RuntimeError(
                    "Bank Mock 回應缺少 bank_code"
                )

            if not v_account:
                raise RuntimeError(
                    "Bank Mock 回應缺少 v_account"
                )

            if not expire_date:
                raise RuntimeError(
                    "Bank Mock 回應缺少 expire_date"
                )

            if not payment_status:
                raise RuntimeError(
                    "Bank Mock 回應缺少 payment_status"
                )

            logger.info(
                "Bank Mock ATM 建立成功: "
                "merchant_trade_no=%s, bank_code=%s",
                merchant_trade_no,
                bank_code,
            )

            # ------------------------------------------------
            # 【修改】
            #
            # 注意：
            #
            # 這裡絕對不產生：
            #
            #     trade_no
            #     provider_transaction_id
            #
            # 因為那是 ECPay Mock Service 的責任。
            # ------------------------------------------------

            return {
                "success": True,
                "merchant_trade_no": str(
                    response_merchant_trade_no
                ),
                "bank_code": str(
                    bank_code
                ),
                "v_account": str(
                    v_account
                ),
                "expire_date": expire_date,
                "payment_status": str(
                    payment_status
                ),
                "response_data": data,
            }

        except ValueError:
            raise

        except RuntimeError:
            raise

        except Exception as exc:

            logger.exception(
                "ECPayMockAdapter.create_atm_payment "
                "發生未預期錯誤"
            )

            raise RuntimeError(
                "Bank Mock ATM 建立失敗"
            ) from exc

    # ========================================================
    # Payment Query
    # ========================================================

    def query_payment(
        self,
        merchant_trade_no: str,
    ) -> Dict[str, Any]:
        """
        【修改】

        暫時不自行猜測 Bank Mock Query API。

        因為目前已知並確認的 Bank Mock endpoint 是：

            /notify/create_account/

        尚未確認 Bank Mock 是否存在一個對應的
        payment query endpoint。

        因此這裡保留 Interface，
        但尚不建立錯誤的 URL。
        """

        raise NotImplementedError(
            "目前尚未定義 Bank Mock Payment Query endpoint"
        )