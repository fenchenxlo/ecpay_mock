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
#     2. 對外部服務進行 HTTPX 呼叫
#     3. 將外部 Response 轉成 Service 可以使用的格式
#
# Adapter 可以：
#     ✅ httpx.post()
#     ✅ httpx.get()
#
# Adapter 不負責：
#     ❌ Django ORM
#     ❌ PaymentRequest.objects.create()
#     ❌ Order.objects.create()
#     ❌ View
#
# ============================================================

import logging
import uuid  # 【新增】
from datetime import datetime
from decimal import Decimal

import httpx
from django.conf import settings

from util.ChkMacVal import (  # 【新增】
    generate_check_mac_value,
)

from ..interface.ecpay_gateway import (
    ECPayATMResult,
    ECPayGateway,
)


logger = logging.getLogger(__name__)


class ECPayMockAdapter(ECPayGateway):
    """
    綠界 Mock Adapter

    用來模擬：

        商城
          ↓
        ECPay Mock
          ↓
        ATM 付款資訊

    真正串接綠界時：

        ECPayMockAdapter
              ↓
        ECPayProductionAdapter

    PaymentService 不需要修改。
    """

# 【修改】
#
# 這個 Adapter 現在位於 ECPay Mock，
# 所以它的 HTTPX 目的地是：
#
#     ECPay Mock
#          ↓ HTTPX
#     Bank Mock
#
# 不是 ECPay Mock 自己。

self.base_url = getattr(
    settings,
    "HF_SPACE_BANK_SITE_URL",
    "",
).rstrip("/")

if not self.base_url:
    # 【新增】
    raise RuntimeError(
        "未設定 HF_SPACE_BANK_SITE_URL"
    )

# ============================================================
# 建立 ATM
# ============================================================

def create_atm_payment(
    self,
    *,
    merchant_trade_no: str,
    trade_amt: Decimal,
    item_name: str,
) -> ECPayATMResult:
    """
    【修改】

    ECPay Mock → Bank Mock。

    ATM 資訊由 Bank Mock 產生：

        bank_code
        v_account
        expire_date

    本 Adapter 負責：

        1. 建立 Request
        2. 產生 CheckMacValue
        3. HTTPX 呼叫 Bank Mock
        4. 解析 Bank Response
        5. 轉成 ECPayATMResult

    不在這裡自行產生：

        ❌ bank_code
        ❌ v_account
        ❌ expire_date
    """

    # ========================================================
    # 【新增】基本驗證
    # ========================================================

    if not merchant_trade_no:
        raise ValueError(
            "merchant_trade_no 不可為空"
        )

    if not item_name:
        raise ValueError(
            "item_name 不可為空"
        )

    try:

        trade_amt = Decimal(
            str(trade_amt)
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

    if trade_amt <= 0:
        raise ValueError(
            "trade_amt 必須大於 0"
        )

    # ========================================================
    # 【新增】
    #
    # Bank Mock API。
    #
    # 正確接口：
    #
    #     /notify/create_account/
    # ========================================================

    url = (
        f"{self.base_url}"
        f"/notify/create_account/"
    )

    # ========================================================
    # 【新增】
    # 建立送往 Bank Mock 的資料
    # ========================================================

    payload = {
        "merchant_trade_no":
            str(merchant_trade_no),

        "trade_amt":
            str(trade_amt),

        "item_name":
            str(item_name),
    }

    # ========================================================
    # 【新增】
    #
    # CheckMacValue
    #
    # 送出前：
    #
    #     payload
    #       ↓
    #     generate_check_mac_value()
    #       ↓
    #     CheckMacValue
    #
    # 不把 CheckMacValue 自己再次放入計算內容。
    # ========================================================

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
            "Bank Mock CheckMacValue 產生失敗"
        )

        raise RuntimeError(
            "Bank Mock Request 簽章失敗"
        ) from ex

    # ========================================================
    # 【新增】
    # HTTPX → Bank Mock
    # ========================================================

    try:

        response = httpx.post(
            url,
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

    # ========================================================
    # 【新增】
    # 解析 Bank Mock JSON
    # ========================================================

    try:

        data = response.json()

    except ValueError as ex:

        logger.exception(
            "Bank Mock Response JSON 解析失敗"
        )

        raise RuntimeError(
            "Bank Mock Response 格式錯誤"
        ) from ex

    if not isinstance(data, dict):

        raise RuntimeError(
            "Bank Mock Response 必須是 Object"
        )

    # ========================================================
    # 【新增】
    # 驗證 Bank Mock 建立結果
    # ========================================================

    if not data.get("status"):

        raise ValueError(
            data.get(
                "message",
                "Bank Mock ATM 建立失敗",
            )
        )

    # ========================================================
    # 【修改】
    #
    # Bank Mock 回傳的是 ATM 資訊本身，
    # 不是：
    #
    #     {"payment": {...}}
    #
    # 所以直接使用 data。
    # ========================================================

    required_fields = [
        "merchant_trade_no",
        "bank_code",
        "v_account",
        "expire_date",
    ]

    missing_fields = [
        field
        for field in required_fields
        if data.get(field) in (
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

    # ========================================================
    # 【新增】
    # 確認 merchant_trade_no
    # ========================================================

    if (
        str(data["merchant_trade_no"])
        != str(merchant_trade_no)
    ):

        logger.error(
            "Bank Mock merchant_trade_no 不一致："
            "expected=%s, actual=%s",
            merchant_trade_no,
            data["merchant_trade_no"],
        )

        raise RuntimeError(
            "Bank Mock 回傳訂單編號不一致"
        )

    # ========================================================
    # 【新增】
    # 解析付款期限
    # ========================================================

    try:

        expire_date = datetime.fromisoformat(
            str(
                data["expire_date"]
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

    # ========================================================
    # 【新增】
    #
    # ECPay trade_no
    #
    # Bank Mock 不負責產生 ECPay trade_no。
    #
    # 因此由 ECPay Mock Adapter 產生。
    # ========================================================

    trade_no = (
        f"EP"
        f"{uuid.uuid4().hex[:18].upper()}"
    )

    # ========================================================
    # 【新增】
    #
    # 將 Bank Mock Response
    # 轉成 ECPayGateway 定義的 ECPayATMResult。
    # ========================================================

    return ECPayATMResult(

        merchant_trade_no=
            str(
                data[
                    "merchant_trade_no"
                ]
            ),

        trade_no=
            trade_no,

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

        # 【新增】
        #
        # 這個 CheckMacValue 是
        # ECPay Mock → Bank Mock
        # Request 使用的簽章。
        #
        # 保存它供上層使用。
        check_mac_value=
            check_mac_value,
    )

    # ========================================================
    # 查詢付款
    # ========================================================

    def query_payment(
        self,
        *,
        merchant_trade_no: str,
    ) -> dict:
        """
        【修改】

        查詢 ECPay Mock 付款狀態。
        """

        if not self.base_url:
            raise RuntimeError(
                "未設定 ECPAY_MOCK_URL"
            )

        url = (
            f"{self.base_url}"
            f"/gateway/payment_info/"
        )

        payload = {
            "merchant_trade_no":
                merchant_trade_no,
        }

        try:
            response = httpx.post(
                url,
                json=payload,
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
                "ECPay Mock Query HTTP 錯誤"
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

        try:
            data = response.json()

        except ValueError as ex:
            logger.exception(
                "ECPay Mock Query JSON 解析失敗"
            )
            raise RuntimeError(
                "ECPay Mock Query Response 格式錯誤"
            ) from ex

        if not isinstance(data, dict):
            raise RuntimeError(
                "ECPay Mock Query Response 必須是 Object"
            )

        return data