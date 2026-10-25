# ============================================================
# ECPay Mock
# gateway/adapter/ecpay_mock_adapter.py
# ============================================================
#
# Adapter Layer
#
# 【本次修改】
#
# Adapter 的責任：
#
#     1. 實作 ECPayGateway Interface
#     2. 使用 HTTPX 呼叫 Bank Mock
#     3. 產生 ECPay Mock → Bank Mock 的 CheckMacValue
#     4. 解析 Bank Mock Response
#     5. 將 ATM 資訊轉成 ECPayATMResult
#
# Adapter 不負責：
#
#     ❌ Django ORM
#     ❌ PaymentRequest
#     ❌ View
#     ❌ 產生 bank_code
#     ❌ 產生 v_account
#     ❌ 產生 expire_date
#     ❌ 產生 trade_no
#
# ATM 流程：
#
#     ECPayService
#          ↓
#     ECPayGateway
#          ↓
#     ECPayMockAdapter
#          ↓ HTTPX
#     Bank Mock
#          ↓
#     bank_code
#     v_account
#     expire_date
#          ↓
#     ECPayMockAdapter
#          ↓
#     ECPayService
#          ↓
#     TradeNo
#          ↓
#     PaymentRequest
#
# ============================================================

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict

import httpx
from django.conf import settings

from util.ChkMacVal import (
    generate_check_mac_value,
)

from ..interface.ecpay_gateway import (
    ECPayATMResult,
    ECPayGateway,
)


logger = logging.getLogger(__name__)


class ECPayMockAdapter(ECPayGateway):
    """
    ECPay Mock Adapter。

    ATM 建立流程：

        ECPayService
             ↓
        ECPayGateway
             ↓
        ECPayMockAdapter
             ↓ HTTPX
        Bank Mock
             ↓
        ATM 資訊
             ↓
        ECPayService

    注意：

    Bank Mock 不負責 ECPay TradeNo。

    TradeNo 由：
    
        ECPayService

    產生。
    """

    def __init__(
        self,
        *,
        timeout: float = 10.0,
    ):
        """
        【修改】

        初始化 Adapter。

        本 Adapter 同時可能有兩個外部 URL：

            1. Bank Mock
               → ATM 建立

            2. ECPay Mock
               → Query API

        因此不能只使用一個 base_url。
        """

        # ====================================================
        # 【保留】
        # HTTPX timeout
        # ====================================================

        self.timeout = timeout

        # ====================================================
        # 【新增】
        #
        # ECPay Mock 自己的 URL。
        #
        # query_payment() 使用。
        # ====================================================

        self.ecpay_mock_url = (
            getattr(
                settings,
                "ECPAY_MOCK_URL",
                "",
            )
            or getattr(
                settings,
                "HF_SPACE_ECPAY_MOCK_URL",
                "",
            )
        ).rstrip("/")

        # ====================================================
        # 【新增】
        #
        # Bank Mock URL。
        #
        # create_atm_payment() 使用。
        # ====================================================

        self.bank_mock_url = (
            getattr(
                settings,
                "HF_SPACE_BANK_SITE_URL",
                "",
            )
            .rstrip("/")
        )

        if not self.bank_mock_url:

            raise RuntimeError(
                "未設定 HF_SPACE_BANK_SITE_URL"
            )

        # ====================================================
        # 【新增】
        #
        # Bank Mock 建立虛擬帳號接口。
        # ====================================================

        self.bank_create_account_url = (
            f"{self.bank_mock_url}"
            f"/notify/create_account/"
        )

    # ========================================================
    # 建立 ATM
    # ========================================================

    def create_atm_payment(
        self,
        payload: Dict[str, Any],
    ) -> ECPayATMResult:
        """
        【修改】

        建立 ATM。

        這裡實際呼叫的是：

            Bank Mock

        Bank Mock 只需要產生：

            bank_code
            v_account
            expire_date

        不要求：

            ❌ trade_no

        TradeNo 由 ECPayService 在取得
        ATM 資訊後產生。
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

        # ====================================================
        # 【新增】
        # 驗證交易金額
        # ====================================================

        try:

            trade_amt_decimal = Decimal(
                str(
                    trade_amt
                )
            )

        except (
            TypeError,
            ValueError,
        ) as ex:

            logger.exception(
                "trade_amt Decimal 轉換失敗"
            )

            raise ValueError(
                "trade_amt 格式錯誤"
            ) from ex

        if trade_amt_decimal <= 0:

            raise ValueError(
                "trade_amt 必須大於 0"
            )

        # ====================================================
        # 【新增】
        #
        # 建立送往 Bank Mock 的 payload。
        #
        # 使用完整 payload，
        # 保留未來綠界欄位擴充能力。
        # ====================================================

        bank_payload = dict(
            payload
        )

        # ====================================================
        # 【修改】
        #
        # 上一個 HTTP 邊界：
        #
        #     Store
        #       ↓
        #     ECPay Mock
        #
        # 的 CheckMacValue
        #
        # 不直接轉給 Bank Mock。
        #
        # 現在建立新的 HTTP 邊界：
        #
        #     ECPay Mock
        #       ↓
        #     Bank Mock
        #
        # 所以要重新計算新的 MAC。
        # ====================================================

        bank_payload.pop(
            "CheckMacValue",
            None,
        )

        # ====================================================
        # 【修改】
        #
        # 確保送給 Bank Mock 的基本欄位格式一致。
        # ====================================================

        bank_payload[
            "merchant_trade_no"
        ] = str(
            merchant_trade_no
        )

        bank_payload[
            "trade_amt"
        ] = str(
            trade_amt_decimal
        )

        bank_payload[
            "item_name"
        ] = str(
            item_name
        )

        # ====================================================
        # 【新增】
        # ATM 固定使用 ATM
        # ====================================================

        bank_payload[
            "choose_payment"
        ] = "ATM"

        # ====================================================
        # 【新增】
        #
        # ECPay Mock → Bank Mock
        # CheckMacValue。
        #
        # 計算時：
        #
        #     不包含 CheckMacValue
        #
        # 計算完成後：
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
                    bank_payload,
                    hash_key,
                    hash_iv,
                )
            )

            signed_payload = {
                **bank_payload,
                "CheckMacValue":
                    check_mac_value,
            }

        except Exception as ex:

            logger.exception(
                "Bank Mock CheckMacValue 產生失敗"
            )

            raise RuntimeError(
                "Bank Mock Request 簽章失敗"
            ) from ex

        # ====================================================
        # 【新增】
        #
        # ECPay Mock → Bank Mock
        #
        # HTTPX
        # ====================================================

        try:

            response = httpx.post(
                self.bank_create_account_url,
                json=signed_payload,
                timeout=self.timeout,
            )

            response.raise_for_status()

        except httpx.TimeoutException as ex:

            logger.exception(
                "Bank Mock ATM Request Timeout"
            )

            raise RuntimeError(
                "Bank Mock 連線逾時"
            ) from ex

        except httpx.HTTPStatusError as ex:

            logger.exception(
                "Bank Mock HTTP 錯誤：%s",
                ex.response.status_code,
            )

            raise RuntimeError(
                "Bank Mock HTTP Request 失敗"
            ) from ex

        except httpx.RequestError as ex:

            logger.exception(
                "Bank Mock HTTPX Request 失敗"
            )

            raise RuntimeError(
                "Bank Mock 無法連線"
            ) from ex

        except Exception as ex:

            logger.exception(
                "Bank Mock Request 發生未知錯誤"
            )

            raise RuntimeError(
                "Bank Mock Request 失敗"
            ) from ex

        # ====================================================
        # 【新增】
        # 解析 Bank Mock JSON
        # ====================================================

        try:

            data = response.json()

        except ValueError as ex:

            logger.exception(
                "Bank Mock Response JSON 解析失敗"
            )

            raise RuntimeError(
                "Bank Mock Response 格式錯誤"
            ) from ex

        # ====================================================
        # 【新增】
        # Response 必須是 Object
        # ====================================================

        if not isinstance(
            data,
            dict,
        ):

            raise RuntimeError(
                "Bank Mock Response 必須是 Object"
            )

        # ====================================================
        # 【新增】
        # 驗證 Bank Mock 執行成功
        # ====================================================

        if not data.get("status"):

            raise ValueError(
                data.get(
                    "message",
                    "Bank Mock ATM 建立失敗",
                )
            )

        # ====================================================
        # 【新增】
        #
        # Bank Mock 回傳的 ATM 核心資訊：
        #
        #     bank_code
        #     v_account
        #     expire_date
        #
        # 注意：
        #
        # ❌ 不要求 trade_no
        # ====================================================

        required_fields = [
            "merchant_trade_no",
            "bank_code",
            "v_account",
            "expire_date",
        ]

        missing_fields = [
            field
            for field in required_fields
            if data.get(field)
            in (
                None,
                "",
            )
        ]

        if missing_fields:

            raise RuntimeError(
                "Bank Mock ATM Response 缺少欄位："
                + ", ".join(
                    missing_fields
                )
            )

        # ====================================================
        # 【新增】
        #
        # 確認 Bank Mock 沒有竄改
        # merchant_trade_no。
        # ====================================================

        if (
            str(
                data[
                    "merchant_trade_no"
                ]
            )
            != str(
                merchant_trade_no
            )
        ):

            logger.error(
                "Bank Mock merchant_trade_no 不一致："
                "expected=%s, actual=%s",
                merchant_trade_no,
                data[
                    "merchant_trade_no"
                ],
            )

            raise RuntimeError(
                "Bank Mock 回傳訂單編號不一致"
            )

        # ====================================================
        # 【新增】
        # 解析 expire_date
        # ====================================================

        try:

            expire_date = datetime.fromisoformat(
                str(
                    data[
                        "expire_date"
                    ]
                )
            )

        except (
            TypeError,
            ValueError,
        ) as ex:

            logger.exception(
                "Bank Mock expire_date 格式錯誤"
            )

            raise RuntimeError(
                "ATM 付款期限格式錯誤"
            ) from ex

        # ====================================================
        # 【修改】
        #
        # 注意：
        #
        # Bank Mock 不產生 TradeNo。
        #
        # 因此這裡不從：
        #
        #     data["trade_no"]
        #
        # 取得 TradeNo。
        #
        # TradeNo 稍後由：
        #
        #     ECPayService
        #
        # 產生。
        #
        # 如果目前 ECPayATMResult 的 trade_no
        # 欄位仍是必填字串，
        # 這裡暫時保留空字串作為「尚未產生」狀態。
        # ====================================================

        return ECPayATMResult(

            merchant_trade_no=
                str(
                    data[
                        "merchant_trade_no"
                    ]
                ),

            # 【修改】
            #
            # TradeNo 尚未產生。
            # 由 ECPayService 後續產生。
            trade_no="",

            bank_code=
                str(
                    data[
                        "bank_code"
                    ]
                ),

            v_account=
                str(
                    data[
                        "v_account"
                    ]
                ),

            expire_date=
                expire_date,

            status=
                str(
                    data.get(
                        "payment_status",
                        "pending",
                    )
                ),

            # =================================================
            # 【新增】
            #
            # 這是：
            #
            # ECPay Mock → Bank Mock
            #
            # Request 的 CheckMacValue。
            # =================================================

            check_mac_value=
                check_mac_value,
        )

    # ========================================================
    # 查詢付款
    # ========================================================

    def query_payment(
        self,
        merchant_trade_no: str,
    ) -> Dict[str, Any]:
        """
        【修改】

        查詢 ECPay Mock 付款狀態。

        注意：

        create_atm_payment() 使用：

            Bank Mock

        query_payment() 則使用：

            ECPay Mock

        兩者 URL 不可以混用。
        """

        if not merchant_trade_no:

            raise ValueError(
                "merchant_trade_no 不可為空"
            )

        # ====================================================
        # 【新增】
        # 驗證 ECPay Mock URL
        # ====================================================

        if not self.ecpay_mock_url:

            raise RuntimeError(
                "未設定 ECPAY_MOCK_URL"
            )

        # ====================================================
        # 【保留】
        # ECPay Mock Query API
        # ====================================================

        url = (
            f"{self.ecpay_mock_url}"
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
        # Query Request 的 CheckMacValue。
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
                "ECPay Query CheckMacValue 產生失敗"
            )

            raise RuntimeError(
                "ECPay Query Request 簽章失敗"
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
        # JSON Response
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