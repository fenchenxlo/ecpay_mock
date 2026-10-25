# ============================================================
# ECPay Mock
# gateway/service/payment_service.py
# ============================================================
#
# Service Layer
#
# 【本次修改】
#
# PaymentService 的責任：
#
#     1. 處理 ECPay Mock 付款業務邏輯
#     2. 建立 ATM Payment
#     3. 呼叫 ECPayGateway Interface
#     4. 驗證 Gateway 回傳的 ATM 資料
#     5. 建立 PaymentRequest
#     6. 查詢 PaymentRequest
#     7. 查詢付款狀態
#
# PaymentService 不負責：
#
#     ❌ Django View
#     ❌ HTTP Request / Response
#     ❌ httpx.post()
#     ❌ 直接呼叫 Bank Mock API
#     ❌ CheckMacValue 計算
#     ❌ CheckMacValue 驗證
#     ❌ 產生銀行 ATM 資訊
#
# HTTPX：
#
#     PaymentService
#          ↓
#     ECPayGateway
#          ↓
#     ECPayMockAdapter
#          ↓
#     HTTPX
#
# ATM 資訊：
#
#     ECPayMockAdapter
#          ↓
#     Bank Mock
#          ↓
#     bank_code
#     v_account
#     expire_date
#
# ECPay 交易編號：
#
#     ECPayService / ECPay Mock
#          ↓
#     provider_transaction_id
#
# Bank Mock 不負責產生 trade_no。
#
# ============================================================


import logging

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional


from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone


# ============================================================
# PaymentRequest
# ============================================================
#
# 【保留】
#
# PaymentRequest 位於：
#
#     Ecpay_mock/gateway/models.py
#
# 本檔案位置：
#
#     Ecpay_mock/gateway/service/payment_service.py
#
# 因此使用：
#
#     from ..models import PaymentRequest
#
# 不可以使用：
#
#     ❌ from commerce_shop.models import PaymentRequest
# ============================================================

from ..models import PaymentRequest


# ============================================================
# ECPayGateway Interface
# ============================================================
#
# 【保留】
#
# Gateway 位於：
#
#     Ecpay_mock/gateway/interface/ecpay_gateway.py
# ============================================================

from ..interface.ecpay_gateway import ECPayGateway


# ============================================================
# Logger
# ============================================================
#
# 【新增】
#
# Service Layer 必須有自己的 logger。
#
# 注意：
#
# ❌ 不記錄 HashKey
# ❌ 不記錄 HashIV
# ❌ 不記錄完整 CheckMacValue
#
# 可以記錄：
#
# ✅ merchant_trade_no
# ✅ trade_no
# ✅ bank_code
# ✅ payment status
# ✅ 錯誤類型
#
# ============================================================

logger = logging.getLogger(__name__)


# ============================================================
# PaymentService
# ============================================================

class PaymentService:
    """
    ECPay Mock Payment Service。

    ========================================================
    ATM 建立流程
    ========================================================

        View
          │
          ▼
        ECPayService
          │
          ▼
        PaymentService
          │
          ▼
        ECPayGateway
          │
          ▼
        ECPayMockAdapter
          │
          │ HTTPX
          ▼
        Bank Mock
          │
          ▼
        bank_code
        v_account
        expire_date

    ========================================================

    PaymentService 收到 Gateway 結果後：

        1. 驗證 Gateway Result
        2. 取得 ECPay trade_no
        3. 取得 Bank ATM 資訊
        4. 建立 PaymentRequest
        5. 回傳 PaymentRequest

    ========================================================

    注意：

        Bank Mock：
            只產生 ATM 資訊

        ECPay Mock：
            負責 ECPay transaction / trade_no

    ========================================================
    """

    def __init__(
        self,
        ecpay_gateway: ECPayGateway,
        merchant_id: str = "2000132",
    ):
        """
        【保留】

        建立 PaymentService。

        Parameters
        ----------
        ecpay_gateway:
            ECPayGateway Interface。

        merchant_id:
            ECPay Mock 商店代號。
        """

        # ====================================================
        # 【保留】
        # ====================================================

        self.ecpay_gateway = ecpay_gateway

        # ====================================================
        # 【保留】
        # ====================================================

        self.merchant_id = merchant_id

    # ========================================================
    # 工具：取得 callback URL
    # ========================================================

    @staticmethod
    def _get_default_return_url() -> str:
        """
        【新增】

        取得預設 ReturnURL。
        """

        base_url = (
            getattr(
                settings,
                "HF_SPACE_E_COMMERCE_URL",
                "",
            )
            or ""
        ).rstrip("/")

        if not base_url:
            return ""

        return (
            f"{base_url}"
            "/commerce_shop/ecpay_mock_notify/"
        )

    # ========================================================

    @staticmethod
    def _get_default_payment_info_url() -> str:
        """
        【新增】

        取得預設 PaymentInfoUrl。
        """

        base_url = (
            getattr(
                settings,
                "HF_SPACE_E_COMMERCE_URL",
                "",
            )
            or ""
        ).rstrip("/")

        if not base_url:
            return ""

        return (
            f"{base_url}"
            "/commerce_shop/payment_info/"
        )

    # ========================================================

    @staticmethod
    def _get_default_order_result_url() -> str:
        """
        【新增】

        取得預設 OrderResultURL。
        """

        base_url = (
            getattr(
                settings,
                "HF_SPACE_E_COMMERCE_URL",
                "",
            )
            or ""
        ).rstrip("/")

        if not base_url:
            return ""

        return (
            f"{base_url}"
            "/commerce_shop/payment_ok/"
        )

    # ========================================================
    # 工具：解析 expire_date
    # ========================================================

    @staticmethod
    def _normalize_expire_date(
        expire_date: Any,
    ):
        """
        【新增】

        將 Gateway / Bank Mock 回傳的 expire_date
        統一轉成 Django DateTimeField 可以使用的 datetime。

        允許：

            datetime
            ISO datetime string
            "%Y-%m-%d %H:%M:%S"
            "%Y/%m/%d %H:%M:%S"

        回傳：

            timezone-aware datetime
        """

        if expire_date is None:
            raise ValueError(
                "ATM 缺少 expire_date"
            )

        # ----------------------------------------------------
        # datetime
        # ----------------------------------------------------

        if isinstance(
            expire_date,
            datetime,
        ):

            result = expire_date

            if timezone.is_naive(result):

                result = timezone.make_aware(
                    result,
                    timezone.get_current_timezone(),
                )

            return result

        # ----------------------------------------------------
        # string
        # ----------------------------------------------------

        if isinstance(
            expire_date,
            str,
        ):

            value = expire_date.strip()

            if not value:
                raise ValueError(
                    "ATM expire_date 不可為空"
                )

            # ------------------------------------------------
            # 嘗試 ISO 8601
            # ------------------------------------------------

            try:

                result = datetime.fromisoformat(
                    value.replace(
                        "Z",
                        "+00:00",
                    )
                )

                if timezone.is_naive(result):

                    result = timezone.make_aware(
                        result,
                        timezone.get_current_timezone(),
                    )

                return result

            except ValueError:
                pass

            # ------------------------------------------------
            # 嘗試常見 ECPay / Bank Mock 格式
            # ------------------------------------------------

            supported_formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y/%m/%d %H:%M",
            ]

            for date_format in supported_formats:

                try:

                    result = datetime.strptime(
                        value,
                        date_format,
                    )

                    result = timezone.make_aware(
                        result,
                        timezone.get_current_timezone(),
                    )

                    return result

                except ValueError:
                    continue

        raise ValueError(
            "ATM expire_date 格式錯誤"
        )

    # ========================================================
    # 工具：驗證 Gateway Result
    # ========================================================

    def _validate_atm_result(
        self,
        *,
        atm_result: Any,
        merchant_trade_no: str,
    ) -> Dict[str, Any]:
        """
        【新增】

        驗證 ECPayMockAdapter 回傳的 dict。

        目前 Adapter 的正式回傳格式：

            {
                "success": True,
                "provider_transaction_id": "...",
                "bank_code": "...",
                "v_account": "...",
                "expire_date": "...",
                "response_data": {...},
            }

        注意：

            provider_transaction_id
            =
            ECPay Mock transaction ID

        不是：

            Bank Mock transaction ID
        """

        # ====================================================
        # 【新增】
        # Result 必須是 dict
        # ====================================================

        if not isinstance(
            atm_result,
            dict,
        ):

            logger.error(
                "ECPay Gateway ATM Result 型別錯誤："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise RuntimeError(
                "ECPay Gateway ATM Result 必須是 Object"
            )

        # ====================================================
        # 【新增】
        # success
        # ====================================================

        if not atm_result.get("success"):

            message = (
                atm_result.get(
                    "message"
                )
                or
                "ECPay Mock ATM 建立失敗"
            )

            logger.error(
                "ECPay Gateway ATM 建立失敗："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise RuntimeError(
                message
            )

        # ====================================================
        # 【新增】
        # provider_transaction_id
        # ====================================================

        provider_transaction_id = (
            atm_result.get(
                "provider_transaction_id"
            )
        )

        if not provider_transaction_id:

            logger.error(
                "ECPay Gateway 缺少 "
                "provider_transaction_id："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise RuntimeError(
                "ECPay Gateway 未回傳 ECPay trade_no"
            )

        # ====================================================
        # 【新增】
        # bank_code
        # ====================================================

        bank_code = (
            atm_result.get(
                "bank_code"
            )
        )

        if not bank_code:

            logger.error(
                "ECPay Gateway 缺少 bank_code："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise RuntimeError(
                "ECPay Gateway 缺少 bank_code"
            )

        # ====================================================
        # 【新增】
        # v_account
        # ====================================================

        v_account = (
            atm_result.get(
                "v_account"
            )
        )

        if not v_account:

            logger.error(
                "ECPay Gateway 缺少 v_account："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise RuntimeError(
                "ECPay Gateway 缺少 v_account"
            )

        # ====================================================
        # 【新增】
        # expire_date
        # ====================================================

        expire_date = (
            atm_result.get(
                "expire_date"
            )
        )

        if not expire_date:

            logger.error(
                "ECPay Gateway 缺少 expire_date："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise RuntimeError(
                "ECPay Gateway 缺少 expire_date"
            )

        # ====================================================
        # 【新增】
        # 統一 expire_date
        # ====================================================

        try:

            normalized_expire_date = (
                self._normalize_expire_date(
                    expire_date
                )
            )

        except ValueError as ex:

            logger.warning(
                "ATM expire_date 驗證失敗："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise ValueError(
                str(ex)
            ) from ex

        # ====================================================
        # 【新增】
        # 確認 ATM 尚未過期
        # ====================================================

        now = timezone.now()

        if normalized_expire_date <= now:

            logger.warning(
                "ATM 付款期限已過期："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise ValueError(
                "ATM 付款期限必須晚於目前時間"
            )

        # ====================================================
        # 【新增】
        # response_data
        # ====================================================

        response_data = (
            atm_result.get(
                "response_data"
            )
        )

        if response_data is None:
            response_data = {}

        if not isinstance(
            response_data,
            dict,
        ):

            logger.warning(
                "ECPay Gateway response_data "
                "不是 Object：merchant_trade_no=%s",
                merchant_trade_no,
            )

            response_data = {}

        # ====================================================
        # 【新增】
        # MerchantTradeNo 一致性驗證
        #
        # Adapter 正式回傳沒有直接放：
        #
        #     merchant_trade_no
        #
        # 所以從 response_data.payment 檢查。
        # ====================================================

        payment_data = response_data.get(
            "payment"
        )

        if isinstance(
            payment_data,
            dict,
        ):

            response_merchant_trade_no = (
                payment_data.get(
                    "merchant_trade_no"
                )
            )

            if response_merchant_trade_no:

                if (
                    str(
                        response_merchant_trade_no
                    )
                    !=
                    str(
                        merchant_trade_no
                    )
                ):

                    logger.error(
                        "Gateway merchant_trade_no 不一致："
                        "expected=%s, actual=%s",
                        merchant_trade_no,
                        response_merchant_trade_no,
                    )

                    raise RuntimeError(
                        "Gateway 回傳的商店訂單編號不一致"
                    )

        # ====================================================
        # 【新增】
        # 完整 ATM Result
        # ====================================================

        return {
            "provider_transaction_id": str(
                provider_transaction_id
            ),

            "bank_code": str(
                bank_code
            ),

            "v_account": str(
                v_account
            ),

            "expire_date": (
                normalized_expire_date
            ),

            "response_data": (
                response_data
            ),
        }

    # ========================================================
    # ATM 建立付款
    # ========================================================

    def create_payment(
        self,
        *,
        order,
        item_name: str,
        choose_payment: str,
        request_data: Optional[Dict[str, Any]] = None,
    ):
        """
        【修改】

        建立 ECPay Mock PaymentRequest。

        ====================================================
        ATM
        ====================================================

            PaymentService
                 │
                 ▼
            ECPayGateway
                 │
                 ▼
            ECPayMockAdapter
                 │
                 │ HTTPX
                 ▼
            Bank Mock
                 │
                 ▼
            ATM 資訊
                 │
                 ▼
            PaymentService
                 │
                 ▼
            PaymentRequest

        ====================================================

        request_data 用途：

            保存原本 Store → ECPay Mock
            邊界帶進來的資料，例如：

                CheckMacValue
                ReturnURL
                PaymentInfoUrl
                OrderResultURL
                merchant_trade_date
                trade_desc

        PaymentService 不驗證 CheckMacValue。

        CheckMacValue 的驗證必須在 View boundary 完成。
        """

        # ====================================================
        # 【新增】
        # request_data 型別驗證
        # ====================================================

        if request_data is None:

            request_data = {}

        if not isinstance(
            request_data,
            dict,
        ):

            logger.warning(
                "PaymentService request_data "
                "型別錯誤"
            )

            raise ValueError(
                "request_data 必須是 Object"
            )

        # ====================================================
        # 【新增】
        # 付款方式驗證
        # ====================================================

        if choose_payment not in (
            "ATM",
            "COD",
        ):

            logger.warning(
                "不支援的付款方式：%s",
                choose_payment,
            )

            raise ValueError(
                "不支援的付款方式"
            )

        # ====================================================
        # 【保留】
        #
        # COD 不需要建立 ATM PaymentRequest。
        # ====================================================

        if choose_payment == "COD":

            logger.info(
                "COD 不建立 ECPay ATM PaymentRequest"
            )

            return None

        # ====================================================
        # 【修改】
        #
        # ECPay Mock ATM 目前只處理 ATM。
        # ====================================================

        if choose_payment != "ATM":

            logger.warning(
                "無法建立 ATM PaymentRequest："
                "choose_payment=%s",
                choose_payment,
            )

            raise ValueError(
                "無法建立付款請求"
            )

        # ====================================================
        # 【新增】
        # Order 驗證
        # ====================================================

        if order is None:

            logger.warning(
                "create_payment 收到空的 order"
            )

            raise ValueError(
                "order 不可為 None"
            )

        # ====================================================

        merchant_trade_no = getattr(
            order,
            "order_number",
            None,
        )

        if not merchant_trade_no:

            logger.warning(
                "order 缺少 order_number"
            )

            raise ValueError(
                "order 缺少 order_number"
            )

        # ====================================================

        order_amount = getattr(
            order,
            "amount",
            None,
        )

        if order_amount is None:

            logger.warning(
                "order 缺少 amount："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise ValueError(
                "order 缺少 amount"
            )

        # ====================================================
        # 【新增】
        # 金額轉 Decimal
        # ====================================================

        try:

            trade_amt = Decimal(
                str(order_amount)
            )

        except (
            InvalidOperation,
            TypeError,
            ValueError,
        ) as ex:

            logger.exception(
                "Order amount 無法轉換成 Decimal："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise ValueError(
                "訂單金額格式錯誤"
            ) from ex

        # ====================================================

        if trade_amt <= Decimal("0"):

            logger.warning(
                "訂單金額必須大於 0："
                "merchant_trade_no=%s, amount=%s",
                merchant_trade_no,
                trade_amt,
            )

            raise ValueError(
                "訂單金額必須大於 0"
            )

        # ====================================================
        # 【新增】
        # item_name 驗證
        # ====================================================

        if not item_name:

            logger.warning(
                "item_name 不可為空："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise ValueError(
                "item_name 不可為空"
            )

        # ====================================================
        # 【新增】
        # merchant_trade_no 一律使用 Order
        # ====================================================

        merchant_trade_no = str(
            merchant_trade_no
        )

        # ====================================================
        # 【新增】
        # 既有 PaymentRequest 查詢
        # ====================================================
        #
        # 注意：
        #
        # 這裡不使用：
        #
        # @transaction.atomic
        #
        # 包住整個 create_payment。
        #
        # 原因：
        #
        # Gateway 後面會進行 HTTPX。
        #
        # 不應該：
        #
        #     BEGIN TRANSACTION
        #          ↓
        #     HTTPX
        #          ↓
        #     Bank Mock
        #          ↓
        #     COMMIT
        #
        # 這樣會讓 Database Transaction
        # 長時間持有。
        #
        # ====================================================

        try:

            existing_payment = (
                PaymentRequest.objects
                .filter(
                    merchant_trade_no=(
                        merchant_trade_no
                    )
                )
                .first()
            )

        except Exception as ex:

            logger.exception(
                "查詢既有 PaymentRequest 失敗："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise RuntimeError(
                "查詢付款請求失敗"
            ) from ex

        # ====================================================
        # 【新增】
        # 已存在 PaymentRequest
        # ====================================================

        if existing_payment is not None:

            # ------------------------------------------------
            # 檢查現有付款資料是否完整
            # ------------------------------------------------

            existing_fields = [
                existing_payment.trade_no,
                existing_payment.bank_code,
                existing_payment.v_account,
                existing_payment.expire_date,
            ]

            if all(
                value not in (
                    None,
                    "",
                )
                for value in existing_fields
            ):

                logger.info(
                    "PaymentRequest 已存在，直接重用："
                    "merchant_trade_no=%s",
                    merchant_trade_no,
                )

                return existing_payment

            # ------------------------------------------------
            # 已存在但資料不完整
            # ------------------------------------------------

            logger.warning(
                "PaymentRequest 已存在但 ATM 資料不完整："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise RuntimeError(
                "既有 PaymentRequest 的 ATM 資料不完整"
            )

        # ====================================================
        # 【新增】
        #
        # 組合 ECPay Gateway Request
        #
        # Adapter 現在要求：
        #
        #     create_atm_payment(payload)
        #
        # 不再使用：
        #
        #     create_atm_payment(
        #         merchant_trade_no=...,
        #         trade_amt=...,
        #         item_name=...,
        #     )
        # ====================================================

        merchant_trade_date = request_data.get(
            "merchant_trade_date"
        )

        if not merchant_trade_date:

            order_created_at = getattr(
                order,
                "created_at",
                None,
            )

            if order_created_at:

                merchant_trade_date = (
                    order_created_at
                )

            else:

                merchant_trade_date = timezone.now()

        # ====================================================
        # 【新增】
        # 建立 Gateway Payload
        # ====================================================

        gateway_payload = {
            "merchant_id": (
                request_data.get(
                    "merchant_id"
                )
                or
                self.merchant_id
            ),

            "merchant_trade_no": (
                merchant_trade_no
            ),

            "merchant_trade_date": (
                merchant_trade_date
            ),

            "trade_amt": str(
                trade_amt
            ),

            "trade_desc": (
                request_data.get(
                    "trade_desc"
                )
                or
                "購買商品"
            ),

            "item_name": (
                str(item_name)
            ),

            "choose_payment": "ATM",

            "payment_type": (
                request_data.get(
                    "payment_type"
                )
                or
                "aio"
            ),
        }

        # ====================================================
        # 【新增】
        # 保留使用者原本傳入的其他 ECPay 欄位
        #
        # 注意：
        #
        # CheckMacValue 不在這裡重新計算。
        #
        # Adapter 會建立真正的：
        #
        # Store/ECPayMock HTTP boundary MAC
        #
        # ====================================================

        passthrough_fields = [
            "user_id",
            "receiver_name",
            "receiver_phone",
            "receiver_address",
            "payment_method",
            "ReturnURL",
            "PaymentInfoUrl",
            "OrderResultURL",
        ]

        for field_name in passthrough_fields:

            value = request_data.get(
                field_name
            )

            if value not in (
                None,
                "",
            ):

                gateway_payload[
                    field_name
                ] = value

        # ====================================================
        # 【新增】
        # Gateway Payload Logger
        #
        # 不記錄 CheckMacValue。
        # ====================================================

        logger.info(
            "開始建立 ECPay Mock ATM："
            "merchant_trade_no=%s, amount=%s",
            merchant_trade_no,
            trade_amt,
        )

        # ====================================================
        # 【新增】
        # 呼叫 Gateway
        # ====================================================

        try:

            atm_result = (
                self.ecpay_gateway
                .create_atm_payment(
                    gateway_payload
                )
            )

            logger.info("ECPay Gateway 原始回應: %s", atm_result,)

        except ValueError as ex:

            logger.warning(
                "ECPay Gateway ATM 業務錯誤："
                "merchant_trade_no=%s, error=%s",
                merchant_trade_no,
                ex,
            )

            raise

        except Exception as ex:

            logger.exception(
                "ECPay Gateway ATM 建立失敗："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise RuntimeError(
                "ATM 付款建立失敗"
            ) from ex

        # ====================================================
        # 【新增】
        # 驗證 Gateway Result
        # ====================================================

        try:

            normalized_result = (
                self._validate_atm_result(
                    atm_result=atm_result,
                    merchant_trade_no=(
                        merchant_trade_no
                    ),
                )
            )

        except ValueError:

            raise

        except RuntimeError:

            raise

        except Exception as ex:

            logger.exception(
                "驗證 ECPay Gateway ATM Result 失敗："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise RuntimeError(
                "ATM 回傳資料驗證失敗"
            ) from ex

        # ====================================================
        # 【新增】
        #
        # 取得 ECPay trade_no
        #
        # 正式來源：
        #
        #     provider_transaction_id
        #
        # 這不是 Bank Mock 產生的交易編號。
        #
        # 它代表 ECPay Mock 的交易編號。
        # ====================================================

        trade_no = (
            normalized_result[
                "provider_transaction_id"
            ]
        )

        # ====================================================
        # 【新增】
        # ATM 資訊
        # ====================================================

        bank_code = (
            normalized_result[
                "bank_code"
            ]
        )

        v_account = (
            normalized_result[
                "v_account"
            ]
        )

        expire_date = (
            normalized_result[
                "expire_date"
            ]
        )

        response_data = (
            normalized_result[
                "response_data"
            ]
        )

        # ====================================================
        # 【新增】
        # CheckMacValue
        #
        # 注意：
        #
        # 這個值是：
        #
        # Store → ECPay Mock
        #
        # 的原始 CheckMacValue。
        #
        # PaymentService 不驗證它。
        #
        # View 已經在進 Service 前完成驗證。
        # ====================================================

        check_mac_value = (
            request_data.get(
                "CheckMacValue"
            )
        )

        # 兼容舊命名
        if not check_mac_value:

            check_mac_value = (
                request_data.get(
                    "check_mac_value"
                )
            )

        # ====================================================
        # 【新增】
        # Callback URL
        # ====================================================

        return_url = (
            request_data.get(
                "ReturnURL"
            )
            or
            self._get_default_return_url()
        )

        payment_info_url = (
            request_data.get(
                "PaymentInfoUrl"
            )
            or
            self._get_default_payment_info_url()
        )

        order_result_url = (
            request_data.get(
                "OrderResultURL"
            )
            or
            self._get_default_order_result_url()
        )

        # ====================================================
        # 【新增】
        # Merchant Trade Date 統一
        # ====================================================

        normalized_trade_date = (
            merchant_trade_date
        )

        if isinstance(
            normalized_trade_date,
            str,
        ):

            try:

                normalized_trade_date = (
                    datetime.fromisoformat(
                        normalized_trade_date.replace(
                            "Z",
                            "+00:00",
                        )
                    )
                )

            except ValueError:

                normalized_trade_date = (
                    timezone.now()
                )

        if not isinstance(
            normalized_trade_date,
            datetime,
        ):

            normalized_trade_date = (
                timezone.now()
            )

        if timezone.is_naive(
            normalized_trade_date
        ):

            normalized_trade_date = (
                timezone.make_aware(
                    normalized_trade_date,
                    timezone.get_current_timezone(),
                )
            )

        # ====================================================
        # 【新增】
        # 建立 PaymentRequest
        # ====================================================

        try:

            with transaction.atomic():

                payment_request = (
                    PaymentRequest.objects.create(

                        # ------------------------------------------------
                        # 【保留】
                        # ECPay Mock Merchant ID
                        # ------------------------------------------------

                        merchant_id=(
                            self.merchant_id
                        ),

                        # ------------------------------------------------
                        # 【保留】
                        # 商店訂單編號
                        # ------------------------------------------------

                        merchant_trade_no=(
                            merchant_trade_no
                        ),

                        # ------------------------------------------------
                        # 【修改】
                        # 使用真正的 datetime
                        # ------------------------------------------------

                        merchant_trade_date=(
                            normalized_trade_date
                        ),

                        # ------------------------------------------------
                        # 【修改】
                        # Decimal
                        # ------------------------------------------------

                        trade_amt=(
                            trade_amt
                        ),

                        # ------------------------------------------------
                        # 【保留】
                        # 交易描述
                        # ------------------------------------------------

                        trade_desc=(
                            gateway_payload[
                                "trade_desc"
                            ]
                        ),

                        # ------------------------------------------------
                        # 【保留】
                        # 商品名稱
                        # ------------------------------------------------

                        item_name=(
                            str(item_name)
                        ),

                        # ------------------------------------------------
                        # 【保留】
                        # Payment Type
                        # ------------------------------------------------

                        payment_type=(
                            gateway_payload[
                                "payment_type"
                            ]
                        ),

                        # ------------------------------------------------
                        # 【保留】
                        # ATM
                        # ------------------------------------------------

                        choose_payment="ATM",

                        # ------------------------------------------------
                        # 【修改】
                        #
                        # ECPay trade_no。
                        #
                        # 不來自 Bank Mock。
                        # ------------------------------------------------

                        trade_no=(
                            trade_no
                        ),

                        # ------------------------------------------------
                        # 【新增】
                        # Bank Code
                        # ------------------------------------------------

                        bank_code=(
                            bank_code
                        ),

                        # ------------------------------------------------
                        # 【新增】
                        # Virtual Account
                        # ------------------------------------------------

                        v_account=(
                            v_account
                        ),

                        # ------------------------------------------------
                        # 【新增】
                        # Expire Date
                        # ------------------------------------------------

                        expire_date=(
                            expire_date
                        ),

                        # ------------------------------------------------
                        # 【新增】
                        # ATM 建立完成
                        # ------------------------------------------------

                        status=(
                            "atm_created"
                        ),

                        # ------------------------------------------------
                        # 【保留】
                        #
                        # 原始 Store → ECPay Mock MAC。
                        #
                        # 不重新計算。
                        # ------------------------------------------------

                        check_mac_value=(
                            check_mac_value
                        ),

                        # ------------------------------------------------
                        # 【新增/保留】
                        # Callback URL
                        # ------------------------------------------------

                        return_url=(
                            return_url
                        ),

                        payment_info_url=(
                            payment_info_url
                        ),

                        order_result_url=(
                            order_result_url
                        ),
                    )
                )

        except IntegrityError as ex:

            # ========================================================
            # 【新增】
            #
            # 可能是 concurrent request。
            #
            # PaymentRequest.merchant_trade_no
            # 通常是 unique=True。
            #
            # 第二個 Request 有可能同時建立，
            # 因此這裡重新查詢。
            # ========================================================

            logger.warning(
                "PaymentRequest 建立發生 IntegrityError，"
                "重新查詢：merchant_trade_no=%s",
                merchant_trade_no,
            )

            try:

                existing_payment = (
                    PaymentRequest.objects
                    .filter(
                        merchant_trade_no=(
                            merchant_trade_no
                        )
                    )
                    .first()
                )

            except Exception as query_ex:

                logger.exception(
                    "IntegrityError 後重新查詢 "
                    "PaymentRequest 失敗："
                    "merchant_trade_no=%s",
                    merchant_trade_no,
                )

                raise RuntimeError(
                    "付款資料建立失敗"
                ) from query_ex

            if existing_payment is not None:

                logger.info(
                    "使用 concurrent request 已建立的 "
                    "PaymentRequest：merchant_trade_no=%s",
                    merchant_trade_no,
                )

                return existing_payment

            logger.exception(
                "PaymentRequest IntegrityError，"
                "但查不到既有資料：merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise RuntimeError(
                "建立 PaymentRequest 失敗"
            ) from ex

        except Exception as ex:

            logger.exception(
                "建立 PaymentRequest 失敗："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise RuntimeError(
                "建立 PaymentRequest 失敗"
            ) from ex

        # ====================================================
        # 【新增】
        # 成功 Logger
        #
        # 不記錄 CheckMacValue。
        # ====================================================

        logger.info(
            "ATM PaymentRequest 建立成功："
            "merchant_trade_no=%s, trade_no=%s, "
            "bank_code=%s",
            merchant_trade_no,
            trade_no,
            bank_code,
        )

        # ====================================================
        # 【新增】
        # 最終回傳 PaymentRequest
        # ====================================================

        return payment_request

    # ========================================================
    # 查詢 PaymentRequest
    # ========================================================

    def get_payment(
        self,
        *,
        merchant_trade_no: str,
    ):
        """
        【修改】

        根據 merchant_trade_no 查詢 PaymentRequest。
        """

        # ====================================================
        # 【新增】
        # 輸入驗證
        # ====================================================

        if not merchant_trade_no:

            logger.warning(
                "get_payment 缺少 merchant_trade_no"
            )

            raise ValueError(
                "merchant_trade_no 不可為空"
            )

        merchant_trade_no = str(
            merchant_trade_no
        )

        # ====================================================
        # 【新增】
        # DB 查詢
        # ====================================================

        try:

            payment_request = (
                PaymentRequest.objects
                .filter(
                    merchant_trade_no=(
                        merchant_trade_no
                    )
                )
                .first()
            )

        except Exception as ex:

            logger.exception(
                "查詢 PaymentRequest 失敗："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise RuntimeError(
                "查詢付款請求失敗"
            ) from ex

        # ====================================================
        # 【新增】
        # Logger
        # ====================================================

        if payment_request is None:

            logger.info(
                "找不到 PaymentRequest："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

        else:

            logger.debug(
                "PaymentRequest 查詢成功："
                "merchant_trade_no=%s, status=%s",
                merchant_trade_no,
                payment_request.status,
            )

        return payment_request

    # ========================================================
    # 查詢付款狀態
    # ========================================================

    def query_payment(
        self,
        *,
        merchant_trade_no: str,
    ) -> dict:
        """
        【修改】

        查詢付款狀態。

        流程：

            1. 先查 ECPay Mock 本地 PaymentRequest
            2. 找不到時
               再透過 ECPayGateway 查詢
        """

        # ====================================================
        # 【新增】
        # Input Validation
        # ====================================================

        if not merchant_trade_no:

            logger.warning(
                "query_payment 缺少 merchant_trade_no"
            )

            raise ValueError(
                "merchant_trade_no 不可為空"
            )

        merchant_trade_no = str(
            merchant_trade_no
        )

        # ====================================================
        # 【新增】
        # 先查本地 PaymentRequest
        # ====================================================

        try:

            payment_request = (
                PaymentRequest.objects
                .filter(
                    merchant_trade_no=(
                        merchant_trade_no
                    )
                )
                .first()
            )

        except Exception as ex:

            logger.exception(
                "query_payment 查詢本地 "
                "PaymentRequest 失敗："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise RuntimeError(
                "付款資料查詢失敗"
            ) from ex

        # ====================================================
        # 【新增】
        # Local Hit
        # ====================================================

        if payment_request is not None:

            logger.info(
                "query_payment 使用本地 PaymentRequest："
                "merchant_trade_no=%s, status=%s",
                merchant_trade_no,
                payment_request.status,
            )

            return {
                "status": True,

                "merchant_trade_no": (
                    payment_request.merchant_trade_no
                ),

                "trade_no": (
                    payment_request.trade_no
                ),

                "bank_code": (
                    payment_request.bank_code
                ),

                "v_account": (
                    payment_request.v_account
                ),

                "expire_date": (
                    payment_request.expire_date
                ),

                "payment_status": (
                    payment_request.status
                ),

                "message": (
                    "付款資料查詢成功"
                ),
            }

        # ====================================================
        # 【新增】
        # Local Miss
        # ====================================================

        logger.info(
            "本地找不到 PaymentRequest，"
            "改由 ECPay Gateway 查詢："
            "merchant_trade_no=%s",
            merchant_trade_no,
        )

        # ====================================================
        # 【新增】
        # Gateway Query
        # ====================================================

        try:

            result = (
                self.ecpay_gateway
                .query_payment(
                    merchant_trade_no=(
                        merchant_trade_no
                    )
                )
            )

        except ValueError as ex:

            logger.warning(
                "ECPay Gateway query 業務錯誤："
                "merchant_trade_no=%s, error=%s",
                merchant_trade_no,
                ex,
            )

            raise

        except Exception as ex:

            logger.exception(
                "ECPay Gateway 查詢付款失敗："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise RuntimeError(
                "付款查詢失敗"
            ) from ex

        # ====================================================
        # 【新增】
        # 驗證 Gateway Result
        # ====================================================

        if not isinstance(
            result,
            dict,
        ):

            logger.error(
                "ECPay Gateway Query Result "
                "型別錯誤：merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise RuntimeError(
                "ECPay Query Response 必須是 Object"
            )

        # ====================================================
        # 【新增】
        # Logger
        # ====================================================

        logger.info(
            "ECPay Gateway 付款查詢完成："
            "merchant_trade_no=%s",
            merchant_trade_no,
        )

        return result