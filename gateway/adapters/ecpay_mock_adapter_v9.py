# ============================================================
# ECPay Mock
# gateway/adapters/ecpay_mock_adapter.py
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
    【本次修改】

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
    重要
    ============================================================

    這支檔案名稱：

        ecpay_mock_adapter.py

    不代表它要呼叫 Ecpay Mock 自己。

    它目前真正的下一站是：

        Bank Mock

    ============================================================
    禁止
    ============================================================

    1. 不使用 Django ORM
    2. 不建立 PaymentRequest
    3. 不建立 PaymentNotification
    4. 不修改 Ecpay Mock DB
    5. 不產生虛擬帳號
    6. 不產生 bank_code
    7. 不產生 v_account
    8. 不產生 expire_date
    9. 不產生 ECPay trade_no

    ============================================================
    ATM 三個重要資料的真正來源
    ============================================================

        Bank Mock
            ↓
        bank_code
        v_account
        expire_date

    ECPayService 才負責產生：

        trade_no
    """

    def __init__(
        self,
        timeout: float = 10.0,
    ):
        """
        【本次修改】

        Adapter 初始化。

        ========================================================
        Ecpay Mock → Bank Mock
        ========================================================

        使用：

            HF_SPACE_BANK_SITE_URL

        不使用：

            HF_SPACE_ECPAY_MOCK_URL

        因為：

            HF_SPACE_ECPAY_MOCK_URL
                ↓
            是 E_commerce 呼叫 Ecpay Mock 的入口

        而本 Adapter 的方向是：

            Ecpay Mock
                ↓
            Bank Mock
        """

        try:

            self.timeout = timeout

            # ------------------------------------------------
            # 【本次修改】
            #
            # Ecpay Mock → Bank Mock
            #
            # 這裡不能使用：
            #
            # HF_SPACE_ECPAY_MOCK_URL
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
            # 【本次修改】
            #
            # Bank Mock ATM 建立入口。
            #
            # Bank_Mock gateway：
            #
            #     /notify/create_account/
            # ------------------------------------------------

            self.create_account_url = (
                f"{self.base_url}"
                "/notify/create_account/"
            )

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
        【本次修改】

        Ecpay Mock → Bank Mock。

        ========================================================
        流程
        ========================================================

        1. 驗證 payload
        2. 建立 Bank Mock Request
        3. 重新產生 CheckMacValue
        4. HTTPX POST
        5. 驗證 HTTP status
        6. 解析 JSON
        7. 驗證 Bank Mock 回傳
        8. 回傳 ATM 資訊給 ECPayService

        ========================================================
        本方法不做
        ========================================================

        不自行產生：

            bank_code
            v_account
            expire_date
            trade_no
        """

        try:

            # ==================================================
            # 【本次修改】
            # 基本 payload 驗證
            # ==================================================

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

            merchant_trade_no = str(
                merchant_trade_no
            )

            # ==================================================
            # 【本次修改】
            #
            # ECPay Mock → Bank Mock
            #
            # 建立專用 payload。
            #
            # 不把 Store → Ecpay Mock 的原始 MAC
            # 原封不動傳下去。
            # ==================================================

            bank_payload = {
                "merchant_trade_no": (
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

            # ==================================================
            # 【本次保留】
            #
            # 產生：
            #
            #     Ecpay Mock → Bank Mock
            #
            # 的 CheckMacValue。
            #
            # 這是第二段 MAC。
            # ==================================================

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

            try:

                bank_payload[
                    "CheckMacValue"
                ] = generate_check_mac_value(
                    bank_payload,
                    hash_key,
                    hash_iv,
                )

            except Exception as exc:

                logger.exception(
                    "Bank Mock Request CheckMacValue "
                    "產生失敗"
                )

                raise RuntimeError(
                    "Bank Mock CheckMacValue 產生失敗"
                ) from exc

            logger.info(
                "Ecpay Mock → Bank Mock "
                "create_account: merchant_trade_no=%s",
                merchant_trade_no,
            )

            # ==================================================
            # 【本次保留】
            #
            # HTTPX 僅允許存在 Adapter。
            # ==================================================

            try:

                response = httpx.post(
                    self.create_account_url,
                    json=bank_payload,
                    timeout=self.timeout,
                )

            except httpx.TimeoutException as exc:

                logger.exception(
                    "Bank Mock ATM API 逾時"
                )

                raise RuntimeError(
                    "Bank Mock ATM API 逾時"
                ) from exc

            except httpx.RequestError as exc:

                logger.exception(
                    "Bank Mock ATM API 呼叫失敗"
                )

                raise RuntimeError(
                    "Bank Mock ATM API 呼叫失敗"
                ) from exc

            # ==================================================
            # 【本次保留】
            # HTTP status
            # ==================================================

            try:

                response.raise_for_status()

            except httpx.HTTPStatusError as exc:

                logger.exception(
                    "Bank Mock HTTP status error: %s",
                    response.status_code,
                )

                raise RuntimeError(
                    "Bank Mock HTTP 回應錯誤"
                ) from exc

            # ==================================================
            # 【本次保留】
            # JSON parsing
            # ==================================================

            try:

                data = response.json()

            except ValueError as exc:

                logger.exception(
                    "Bank Mock 回傳非 JSON"
                )

                raise RuntimeError(
                    "Bank Mock 回傳格式錯誤"
                ) from exc

            if not isinstance(
                data,
                dict,
            ):

                raise RuntimeError(
                    "Bank Mock 回傳資料必須是 dict"
                )

            # ==================================================
            # 【本次修改】
            #
            # Bank Mock 的：
            #
            #     status
            #
            # 是「這次 API 處理是否成功」。
            #
            # 它不是：
            #
            #     payment_status
            #
            # 因此不能：
            #
            #     payment_status = data["status"]
            #
            # ==================================================

            if not data.get(
                "status"
            ):

                raise ValueError(
                    data.get(
                        "message",
                        "Bank Mock ATM 建立失敗",
                    )
                )

            # ==================================================
            # 【本次新增】
            #
            # 支援 Bank Mock：
            #
            # ① 直接回傳 ATM 欄位
            #
            # 或：
            #
            # ② payment = {...}
            #
            # ==================================================

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

            # ==================================================
            # 【本次新增】
            # merchant_trade_no
            # ==================================================

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
                str(
                    response_merchant_trade_no
                )
                != merchant_trade_no
            ):

                raise RuntimeError(
                    "Bank Mock merchant_trade_no 不一致"
                )

            # ==================================================
            # 【本次保留】
            #
            # ATM 三項重要資訊必須由 Bank Mock 回傳。
            # ==================================================

            bank_code = result_data.get(
                "bank_code"
            )

            v_account = result_data.get(
                "v_account"
            )

            expire_date = result_data.get(
                "expire_date"
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

            # ==================================================
            # 【本次修改】
            #
            # payment_status 必須明確存在。
            #
            # 不再：
            #
            #     or result_data.get("status")
            #
            # 因為 status=True 是 API 成功，
            # 並非 ATM payment_status。
            # ==================================================

            payment_status = result_data.get(
                "payment_status"
            )

            if not payment_status:

                raise RuntimeError(
                    "Bank Mock 回應缺少 payment_status"
                )

            logger.info(
                "Bank Mock ATM 建立成功: "
                "merchant_trade_no=%s, "
                "bank_code=%s, "
                "v_account=%s, "
                "payment_status=%s"
                "expire_date=%s",
                merchant_trade_no,
                bank_code,
                v_account,
                payment_status,
                expire_date,
            )

            # ==================================================
            # 【本次保留】
            #
            # Adapter 只把 Bank Mock 結果整理回傳。
            #
            # 不產生：
            #
            #     trade_no
            #     provider_transaction_id
            # ==================================================

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

                "expire_date": (
                    expire_date
                ),

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
        【保留】

        Bank Mock Query endpoint 尚未確認。

        因此目前不自行猜測 URL。

        未來如果 Bank Mock 有：

            /notify/query_account/

        或其他正式 Query endpoint，

        再依實際 API 契約補上。
        """

        raise NotImplementedError(
            "目前尚未定義 Bank Mock Payment Query endpoint"
        )