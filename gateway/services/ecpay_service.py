# ============================================================
# ECPay Mock
# gateway/services/ecpay_service.py
# ============================================================

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from django.db import transaction

# 【新增】
from django.conf import settings

from django.utils import timezone

from ..adapters.ecpay_mock_adapter import (
    ECPayMockAdapter,
)

from ..interface.ecpay_gateway import (
    ECPayGateway,
)

# ============================================================
# 【新增】
# Ecpay Mock → E_commerce
# Payment Callback
# ============================================================

# 【修改】
from ..interface.store_payment_gateway import (
    StorePaymentGateway,
    StorePaymentNotifyResult,
)

from ..adapters.store_payment_adapter import (
    StorePaymentAdapter,
)

from ..models import PaymentRequest, PaymentNotification, Order   # 【修改】新增 Order

#from ..repositories.ecpay_repository import (
#    ECPayRepository,
#)


logger = logging.getLogger(__name__)


class ECPayService:
    """
    【修改】

    ECPay Mock ATM 業務 Service。

    ============================================================
    正式流程
    ============================================================

    E_commerce
        ↓
    /gateway/ecpay_gateway_checkout/
        ↓
    ECPayService
        ↓
    ECPayMockAdapter
        ↓ HTTPX
    Bank Mock
        ↓
    bank_code
    v_account
    expire_date
        ↓
    回到 ECPayService
        ↓
    產生 ECPay trade_no
        ↓
    ECPayRepository
        ↓
    PaymentRequest

    ============================================================
    Service 不負責
    ============================================================

    1. 不直接使用 Django ORM <== X
    2. 不使用 httpx
    3. 不計算 CheckMacValue
    4. 不驗證 CheckMacValue
    5. 不產生 bank_code
    6. 不產生 v_account
    7. 不產生 expire_date
    """

    # ============================================================
    # 【修改】
    # ECPayService Dependency Injection
    # ============================================================

    def __init__(
        self,
        ecpay_gateway=None,
        store_payment_gateway=None,
    ):
        """
        【修改】

        ECPayService 使用兩個不同方向的 Gateway。

        ========================================================
        ① Ecpay Mock → Bank Mock
        ========================================================

        ECPayGateway
            ↓
        ECPayMockAdapter

        ========================================================
        ② Ecpay Mock → E_commerce
        ========================================================

        StorePaymentGateway
            ↓
        StorePaymentAdapter

        ========================================================
        注意
        ========================================================

        ECPayGateway 與 StorePaymentGateway
        是兩個不同責任的 Gateway，不可以混用。
        """

        # ========================================================
        # 【保留】
        # Ecpay Mock → Bank Mock
        # ATM Gateway
        # ========================================================

        self.ecpay_gateway = (
            ecpay_gateway
            or ECPayMockAdapter()
        )

        # ========================================================
        # 【新增】
        # Ecpay Mock → E_commerce
        # Payment Callback Gateway
        # ========================================================

        self.store_payment_gateway = (
            store_payment_gateway
            or StorePaymentAdapter()
        )

    # ============================================================
    # 【新增】
    # 查詢已建立的 ATM 付款資訊
    # ============================================================

    def get_atm_payment_info(
        self,
        *,
        merchant_trade_no: str,
    ) -> Dict[str, Any]:
        """
        【新增】

        提供 Ecpay Mock ATM 資訊頁面查詢已建立的
        PaymentRequest。

        ========================================================
        Service 責任
        ========================================================

        1. 驗證 merchant_trade_no
        2. 透過 Repository 查詢 PaymentRequest
        3. 驗證 ATM 資訊是否存在
        4. 整理 Template 所需資料

        ========================================================
        Service 不負責
        ========================================================

        ❌ View / HTTP Response
        ❌ render()
        ❌ Django ORM
        ❌ httpx
        ❌ 產生 ATM 資訊
        """

        if not merchant_trade_no:
            raise ValueError(
                "查詢 ATM 資訊缺少 merchant_trade_no"
            )

        merchant_trade_no = str(
            merchant_trade_no
        ).strip()

        if not merchant_trade_no:
            raise ValueError(
                "merchant_trade_no 不可為空"
            )

        # ========================================================
        # 【新增】
        # 透過 ECPayRepository 查詢 PaymentRequest
        # ========================================================

        payment_request = (
            PaymentRequest.objects
            .filter(
                merchant_trade_no=merchant_trade_no
            )
            .first()
        )

        if payment_request is None:
            raise ValueError(
                "找不到對應的 PaymentRequest"
            )

        # ========================================================
        # 【新增】
        # ATM 資訊完整性驗證
        # ========================================================

        if not payment_request.bank_code:
            raise ValueError(
                "PaymentRequest 缺少 bank_code"
            )

        if not payment_request.v_account:
            raise ValueError(
                "PaymentRequest 缺少 v_account"
            )

        if not payment_request.expire_date:
            raise ValueError(
                "PaymentRequest 缺少 expire_date"
            )

        # ========================================================
        # 【新增】
        # 整理 atm_info.html 所需資料
        # ========================================================

        return {
            "merchant_id": str(
                payment_request.merchant_id
            ),
            "merchant_trade_no": (
                merchant_trade_no
            ),
            "merchant_trade_date": (
                payment_request.merchant_trade_date
            ),
            "trade_amt": str(
                payment_request.trade_amt
            ),
            "trade_desc": (
                payment_request.trade_desc
            ),
            "item_name": (
                payment_request.item_name
            ),
            "choose_payment": (
                payment_request.choose_payment
            ),
            "payment_type": (
                payment_request.payment_type
            ),
            "trade_no": str(
                payment_request.trade_no
            ) if payment_request.trade_no else None,
            "bank_code": str(
                payment_request.bank_code
            ),
            "v_account": str(
                payment_request.v_account
            ),
            "expire_date": (
                payment_request.expire_date
            ),
            "status": (
                payment_request.status
            ),
        }

    # ============================================================
    # 【新增】
    # Ecpay Mock → E_commerce
    # Payment Callback
    # ============================================================

    def _notify_store_payment_result(
        self,
        request_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        【新增】

        將 Ecpay Mock 已處理完成的付款結果通知 E_commerce。

        ========================================================
        Service 責任
        ========================================================

        1. 整理要通知 Store 的 business payload。
        2. 呼叫 StorePaymentGateway。

        ========================================================
        Adapter 責任
        ========================================================

        StorePaymentAdapter 負責：

            payload
                ↓
            CheckMacValue
                ↓
            HTTPX
                ↓
            E_commerce /payment_callback/

        ========================================================
        禁止
        ========================================================

        ❌ httpx.post()
        ❌ CheckMacValue 計算
        ❌ callback URL 處理
        """

        # ========================================================
        # 【新增】
        # 驗證 callback payload
        # ========================================================

        if not isinstance(
            request_data,
            dict,
        ):
            raise ValueError(
                "Store Payment Callback payload 必須是 dict"
            )

        merchant_trade_no = (
            request_data.get(
                "merchant_trade_no"
            )
        )

        if not merchant_trade_no:
            raise ValueError(
                "Store Payment Callback 缺少 merchant_trade_no"
            )

        # ========================================================
        # 【新增】
        # 建立 Store Callback business payload
        #
        # 不直接修改 Service 傳入的 request_data。
        #
        # CheckMacValue 由 StorePaymentAdapter
        # 重新簽章，所以 Service 不處理 MAC。
        # ========================================================

        callback_payload = dict(
            request_data
        )

        # ========================================================
        # 【新增】
        # 移除來源端 CheckMacValue
        #
        # Bank Mock → Ecpay Mock 的 MAC
        # 不可以直接沿用到：
        #
        # Ecpay Mock → E_commerce
        #
        # StorePaymentAdapter 會重新計算新的 MAC。
        # ========================================================

        callback_payload.pop(
            "CheckMacValue",
            None,
        )

        callback_payload.pop(
            "check_mac_value",
            None,
        )

        # ========================================================
        # 【新增】
        # 呼叫 StorePaymentGateway
        #
        # Service 不知道 HTTPX。
        # ========================================================

        result = (
            self.store_payment_gateway
            .notify_payment_result(
                callback_payload
            )
        )
        
        # 【修改】Adapter 現在回傳 dict，不再是 StorePaymentNotifyResult
        # 舊的:
        # if not isinstance(
        #     result,
        #     StorePaymentNotifyResult,
        # ):
        #     raise RuntimeError(
        #         "StorePaymentGateway 回傳格式錯誤"
        #     )
        if not isinstance(result, dict):
            raise RuntimeError(
                "StorePaymentGateway 回傳格式錯誤"
            )

        # 【修改】result.success → result.get("success")
        if not result.get("success"):

            logger.error(
                "E_commerce Payment Callback 失敗："
                "merchant_trade_no=%s, "
                "status_code=%s, "
                "message=%s",
                merchant_trade_no,
                result.get("status_code"),
                result.get("message"),
            )

            raise RuntimeError(
                "E_commerce Payment Callback 失敗"
            )

        logger.info(
            "E_commerce Payment Callback 成功："
            "merchant_trade_no=%s, "
            "status_code=%s",
            merchant_trade_no,
            result.get("status_code"),
        )

        # 【修改】result 本身已經是 dict，直接回傳
        # 舊的:
        # return {
        #     "success": result.success,
        #     "status_code": result.status_code,
        #     "message": result.message,
        #     "response_data": result.response_data,
        # }
        return result        

        # # ========================================================
        # # 【修改】
        # # Gateway 結果驗證
        # #
        # # StorePaymentAdapter
        # # 回傳 StorePaymentNotifyResult。
        # # ========================================================

        # if not isinstance(
            # result,
            # StorePaymentNotifyResult,
        # ):
            # raise RuntimeError(
                # "StorePaymentGateway 回傳格式錯誤"
            # )

        # if not result.success:

            # logger.error(
                # "E_commerce Payment Callback 失敗："
                # "merchant_trade_no=%s, "
                # "status_code=%s, "
                # "message=%s",
                # merchant_trade_no,
                # result.status_code,
                # result.message,
            # )

            # raise RuntimeError(
                # "E_commerce Payment Callback 失敗"
            # )

        # logger.info(
            # "E_commerce Payment Callback 成功："
            # "merchant_trade_no=%s, "
            # "status_code=%s",
            # merchant_trade_no,
            # result.status_code,
        # )

        # # ========================================================
        # # 【新增】
        # # 對 Service 上層統一回傳 dict。
        # #
        # # Gateway 層仍然使用：
        # #
        # #     StorePaymentNotifyResult
        # #
        # # Service 對外則維持目前：
        # #
        # #     Dict[str, Any]
        # #
        # # ========================================================

        # return {
            # "success": result.success,
            # "status_code": result.status_code,
            # "message": result.message,
            # "response_data": result.response_data,
        # }

    # ============================================================
    # 【新增】
    # Bank Mock → Ecpay Mock Payment Notification
    # ============================================================

    def process_payment_notification(
        self,
        *,
        request_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        【新增】

        處理 Bank Mock → Ecpay Mock 的 ATM 付款通知。

        ============================================================
        正式流程
        ============================================================

        Bank Mock
            ↓ HTTPX
        Ecpay Mock View
            ↓
        CheckMacValue 已由 View 驗證
            ↓
        ECPayService
            ↓
        ECPayRepository <== X
            ↓
        PaymentRequest / PaymentNotification
            ↓
        StorePaymentGateway
            ↓
        StorePaymentAdapter
            ↓ HTTPX
        E_commerce

        ============================================================
        Service 責任
        ============================================================

        1. 驗證 callback 業務資料
        2. 找 PaymentRequest
        3. 驗證 merchant_trade_no
        4. 驗證 trade_amt
        5. 判斷 paid / failed
        6. 更新 PaymentRequest
        7. 建立 PaymentNotification
        8. 通知 E_commerce

        ============================================================
        Service 不負責
        ============================================================

        1. 不驗證 CheckMacValue
        2. 不計算 CheckMacValue
        3. 不使用 HTTPX
        """

        try:

            if not isinstance(
                request_data,
                dict,
            ):

                raise ValueError(
                    "payment notification 必須是 dict"
                )

            merchant_trade_no = (
                request_data.get(
                    "merchant_trade_no"
                )
            )

            if not merchant_trade_no:

                raise ValueError(
                    "付款通知缺少 merchant_trade_no"
                )

            merchant_trade_no = str(
                merchant_trade_no
            )

            # ====================================================
            # 【新增】
            # 找既有 PaymentRequest
            # ====================================================

            payment_request = (
                PaymentRequest.objects
                .filter(
                    merchant_trade_no=merchant_trade_no
                )
                .first()
            )

            if payment_request is None:

                raise ValueError(
                    "找不到對應的 PaymentRequest"
                )

            # ====================================================
            # 【新增】
            # 金額驗證
            # ====================================================

            incoming_trade_amt = (
                request_data.get(
                    "trade_amt"
                )
            )

            if incoming_trade_amt in (
                None,
                "",
            ):

                raise ValueError(
                    "付款通知缺少 trade_amt"
                )

            try:

                incoming_amount = Decimal(
                    str(incoming_trade_amt)
                )

            except (
                TypeError,
                ValueError,
            ) as exc:

                raise ValueError(
                    "付款通知 trade_amt 格式錯誤"
                ) from exc

            stored_amount = Decimal(
                str(
                    payment_request.trade_amt
                )
            )

            if incoming_amount != stored_amount:

                raise ValueError(
                    "付款通知 trade_amt 與 PaymentRequest 不一致"
                )

            # ====================================================
            # 【新增】
            # 決定付款結果
            # ====================================================

            payment_status = (
                request_data.get(
                    "payment_status"
                )
            )

            if payment_status is None:

                payment_status = request_data.get(
                    "PaymentStatus"
                )

            if payment_status is None:

                payment_status = request_data.get(
                    "status"
                )

            normalized_status = str(
                payment_status or ""
            ).strip().lower()

            rtn_code = request_data.get(
                "rtn_code"
            )

            if rtn_code is None:

                rtn_code = request_data.get(
                    "RtnCode"
                )

            # ----------------------------------------------------
            # 【新增】
            #
            # Bank Mock 已知結果：
            #
            #     paid
            #     failed
            #
            # 同時支援：
            #
            #     success
            #     succeeded
            #     1
            #     0
            #
            # 避免 callback 命名大小寫不同而失效。
            # ----------------------------------------------------

            success_values = {
                "paid",
                "success",
                "succeeded",
                "1",
            }

            failed_values = {
                "failed",
                "failure",
                "error",
                "0",
                "atm_failed",   # 【新增】Bank Mock simulate_failed 送的是 atm_failed
            }

            # 【新增】逾期未付款：Bank Mock simulate_expired 送的是 atm_expired
            expired_values = {
                "expired",
                "atm_expired",
            }

            # failed_values = {
                # "failed",
                # "failure",
                # "error",
                # "0",
            # }

            # 【新增】逾期旗標（逾期不算付款成功，is_paid 仍為 False）
            is_expired = False

            if normalized_status in success_values:

                is_paid = True

            elif normalized_status in failed_values:

                is_paid = False

            elif normalized_status in expired_values:
                is_paid = False
                is_expired = True

            elif str(
                rtn_code
            ) == "1":

                is_paid = True

            elif str(
                rtn_code
            ) == "0":

                is_paid = False

            else:

                raise ValueError(
                    "無法判斷付款通知結果"
                )

            # ====================================================
            # 【新增】
            # ECPay Mock 自己的 PaymentRequest status
            #
            # 注意：
            # 這不是 Store Order.status。
            # ====================================================

            if is_paid:

                payment_request_status = (
                    "atm_paid"
                )

                normalized_payment_status = (
                    "paid"
                )

                normalized_rtn_code = 1

                default_message = (
                    "ATM 付款成功"
                )

            # 【新增】逾期：PaymentRequest.status 寫 atm_expired（models 本來就有此選項），
            #       並以 status="expired" 通知商城，由商城更新 Order/Payment 與庫存
            elif is_expired:
                payment_request_status = (
                    "atm_expired"
                )
                normalized_payment_status = (
                    "expired"
                )
                normalized_rtn_code = 0
                default_message = (
                    "ATM 逾期未付款"
                )

            else:

                payment_request_status = (
                    "atm_failed"
                )

                normalized_payment_status = (
                    "failed"
                )

                normalized_rtn_code = 0

                default_message = (
                    "ATM 付款失敗"
                )

            # ====================================================
            # 【新增】
            # payment_date
            # ====================================================

            payment_date = (
                self._get_payment_date(
                    request_data
                )
            )

            trade_no = (
                request_data.get(
                    "trade_no"
                )
                or payment_request.trade_no
            )

            if not trade_no:

                raise ValueError(
                    "付款通知缺少 trade_no"
                )

            # ====================================================
            # 【新增】
            # 更新 PaymentRequest
            # ====================================================

            payment_request_data = {
                "status": (
                    payment_request_status
                ),
            }

            # ----------------------------------------------------
            # 【保留】
            #
            # 如果 Bank Mock callback 帶回 ATM 資訊，
            # 同步保存。
            # ----------------------------------------------------

            if request_data.get(
                "bank_code"
            ):

                payment_request_data[
                    "bank_code"
                ] = str(
                    request_data[
                        "bank_code"
                    ]
                )

            if request_data.get(
                "v_account"
            ):

                payment_request_data[
                    "v_account"
                ] = str(
                    request_data[
                        "v_account"
                    ]
                )

            if request_data.get(
                "expire_date"
            ):

                payment_request_data[
                    "expire_date"
                ] = self._normalize_expire_date(
                    request_data[
                        "expire_date"
                    ]
                )
            
            # 【刪除】改到「商店通知成功後」才更新（見步驟 4）
            # for field, value in payment_request_data.items():
                # setattr(
                    # payment_request,
                    # field,
                    # value,
                # )

            # payment_request.save(
                # update_fields=list(
                    # payment_request_data.keys()
                # )
            # )

            # ====================================================
            # 【新增】
            # 建立 PaymentNotification
            # ====================================================

            notification_data = {
                "merchant_trade_no": (
                    merchant_trade_no
                ),
                "trade_no": str(
                    trade_no
                ),
                "trade_amt": (
                    incoming_amount
                ),
                "payment_date": (
                    payment_date
                ),
                "choose_payment": (
                    request_data.get(
                        "choose_payment"
                    )
                    or payment_request.choose_payment
                    or "ATM"
                ),
                "payment_type": (
                    request_data.get(
                        "payment_type"
                    )
                    or payment_request.payment_type
                    or "aio"
                ),
                "rtn_code": (
                    normalized_rtn_code
                ),
                "rtn_msg": (
                    request_data.get(
                        "rtn_msg"
                    )
                    or request_data.get(
                        "RtnMsg"
                    )
                    or default_message
                ),
                "simulate_paid": (
                    is_paid
                ),
            }
            
            # 【刪除】改到「商店通知成功後」才建立（見步驟 4）
            # notification = (
                # PaymentNotification.objects.create(
                    # **notification_data
                # )
            # )

            # ====================================================
            # 【新增】
            #
            # Ecpay Mock → E_commerce
            #
            # 使用新的 Gateway / Adapter。
            #
            # Service 不使用 HTTPX。
            # ====================================================

            # 【新增】payment_request 尚未更新，先取本次通知帶來的 expire_date
            expire_value = (
                payment_request_data.get("expire_date")
                or payment_request.expire_date
            )

            store_payload = {
                "merchant_trade_no": (
                    merchant_trade_no
                ),
                "trade_no": str(
                    trade_no
                ),
                "trade_amt": str(
                    incoming_amount
                ),
                "status": (
                    normalized_payment_status
                ),
                "rtn_code": (
                    normalized_rtn_code
                ),
                # 【修改】notification.rtn_msg → notification_data["rtn_msg"]
                "rtn_msg": (
                    notification_data["rtn_msg"]
                ),
                # 【修改】notification.choose_payment → notification_data[...]
                "choose_payment": (
                    notification_data["choose_payment"]
                ),
                # 【修改】notification.payment_type → notification_data[...]
                "payment_type": (
                    notification_data["payment_type"]
                ),
                "payment_date": (
                    payment_date.isoformat()
                ),
                # 【修改】優先用本次通知的值，沒有才用 DB 舊值
                "bank_code": (
                    payment_request_data.get("bank_code")
                    or payment_request.bank_code
                    or None
                ),
                "v_account": (
                    payment_request_data.get("v_account")
                    or payment_request.v_account
                    or None
                ),
                # 【修改】expire_value 可能是 datetime 或字串，兩種都能處理
                "expire_date": (
                    expire_value.isoformat()
                    if hasattr(expire_value, "isoformat")
                    else (str(expire_value) if expire_value else None)
                ),
            }

            # 【新增】轉傳 Bank 模擬頁的 simulate 標記給商城（商城用它放行逾期訂單改狀態）
            store_payload["simulate"] = str(
                request_data.get("simulate", "")
            )
            
            # store_payload = {
                # "merchant_trade_no": (
                    # merchant_trade_no
                # ),
                # "trade_no": str(
                    # trade_no
                # ),
                # "trade_amt": str(
                    # incoming_amount
                # ),
                # "status": (
                    # normalized_payment_status
                # ),
                # "rtn_code": (
                    # normalized_rtn_code
                # ),
                # "rtn_msg": (
                    # notification.rtn_msg
                # ),
                # "choose_payment": (
                    # notification.choose_payment
                # ),
                # "payment_type": (
                    # notification.payment_type
                # ),
                # "payment_date": (
                    # payment_date.isoformat()
                # ),
                # "bank_code": (
                    # str(
                        # payment_request.bank_code
                    # )
                    # if payment_request.bank_code
                    # else None
                # ),
                # "v_account": (
                    # str(
                        # payment_request.v_account
                    # )
                    # if payment_request.v_account
                    # else None
                # ),
                # "expire_date": (
                    # payment_request.expire_date.isoformat()
                    # if payment_request.expire_date
                    # else None
                # ),
            # }

            try:

                callback_result = (
                    self.store_payment_gateway
                    .notify_payment_result(
                        store_payload
                    )
                )

            except ValueError:
                raise

            except RuntimeError:
                raise

            except Exception as exc:

                logger.exception(
                    "E_commerce Payment Callback 失敗: "
                    "merchant_trade_no=%s",
                    merchant_trade_no,
                )

                raise RuntimeError(
                    "E_commerce Payment Callback 失敗"
                ) from exc

            # ====================================================
            # 【新增】
            # 商店回傳失敗 → 不更新 ecpay DB，把原因往上拋給 Bank
            # ====================================================

            if not callback_result.get("success"):

                raise RuntimeError(
                    "商店處理失敗："
                    f"{callback_result.get('message')}"
                )

            # ====================================================
            # 【新增】
            # 商店成功後，才更新 ecpay DB（同一個 transaction）
            # ====================================================

            with transaction.atomic():

                for field, value in payment_request_data.items():
                    setattr(
                        payment_request,
                        field,
                        value,
                    )

                payment_request.save(
                    update_fields=list(
                        payment_request_data.keys()
                    )
                )

                notification = (
                    PaymentNotification.objects.create(
                        **notification_data
                    )
                )

                # ------------------------------------------------
                # 【新增】同步更新 ecpay_mock Order.status
                #   paid → paid / expired → expired / 其他 → failed
                # 【重點】在商店通知成功後、同一個 transaction 內寫入
                # ------------------------------------------------
                gateway_order = (
                    Order.objects
                    .select_for_update()
                    .filter(order_number=merchant_trade_no)
                    .first()
                )

                if gateway_order:
                    gateway_order.status = (
                        "paid" if is_paid
                        else "expired" if is_expired
                        else "failed"
                    )
                    gateway_order.save(
                        update_fields=["status", "updated_at"]
                    )
                
            return {
                "status": True,
                "message": "付款通知處理成功",
                "payment": {
                    "merchant_trade_no": (
                        merchant_trade_no
                    ),
                    "trade_no": str(
                        trade_no
                    ),
                    "payment_status": (
                        normalized_payment_status
                    ),
                    "rtn_code": (
                        normalized_rtn_code
                    ),
                    "rtn_msg": (
                        notification.rtn_msg
                    ),
                },
                "store_callback": callback_result,
            }

            # return {
                # "status": True,
                # "message": (
                    # "付款通知處理成功"
                # ),
                # "payment": {
                    # "merchant_trade_no": (
                        # merchant_trade_no
                    # ),
                    # "trade_no": str(
                        # trade_no
                    # ),
                    # "payment_status": (
                        # normalized_payment_status
                    # ),
                    # "rtn_code": (
                        # normalized_rtn_code
                    # ),
                    # "rtn_msg": (
                        # notification.rtn_msg
                    # ),
                # },
                # "store_callback": (
                    # callback_result
                # ),
            # }
        except Exception as exc:

            logger.exception(
                "Payment notification 處理失敗: "
                "merchant_trade_no=%s",
                request_data.get("merchant_trade_no"),
            )

            # 【修改】原本只有「付款通知處理失敗」，Bank 頁面看不到原因
            # raise RuntimeError(
            #     "付款通知處理失敗"
            # ) from exc
            raise RuntimeError(
                f"付款通知處理失敗：{exc}"
            ) from exc        

    # ============================================================
    # 【新增】取消訂單（E_commerce → ECPay Mock → Bank Mock）
    # 順序：先通知 Bank（下游）成功，才寫 ecpay_mock 自己的 DB
    # ============================================================

    def cancel_order(
        self,
        *,
        merchant_trade_no: str,
        delete_record: bool = False,   # 【新增】True=刪除已取消的紀錄（商店刪除訂單時呼叫）
    ) -> Dict[str, Any]:

        payment_request = (
            PaymentRequest.objects
            .filter(merchant_trade_no=merchant_trade_no)
            .first()
        )

        # 【新增】刪除模式：先通知 Bank 刪虛擬帳號，成功才刪 ecpay_mock 自己的紀錄（下游先、本地後）。
        # 找不到紀錄視為成功；有紀錄但不是 atm_cancelled 一律拒絕，避免誤刪仍有效的交易
        if delete_record:
            if payment_request is not None and payment_request.status != "atm_cancelled":
                raise ValueError(
                    f"此交易狀態為 {payment_request.status}，請先取消訂單再刪除"
                )

            self.ecpay_gateway.cancel_account(merchant_trade_no, delete_record=True)

            with transaction.atomic():
                PaymentNotification.objects.filter(
                    merchant_trade_no=merchant_trade_no
                ).delete()
                PaymentRequest.objects.filter(
                    merchant_trade_no=merchant_trade_no
                ).delete()
                Order.objects.filter(
                    order_number=merchant_trade_no
                ).delete()

            return {
                "status": True,
                "merchant_trade_no": merchant_trade_no,
                "payment_status": "deleted",
            }

        if payment_request is None:
            raise LookupError("找不到 ATM 付款紀錄")

        # 【新增】已付款 / 已逾期的交易不可取消
        if payment_request.status in ("atm_paid", "atm_expired"):
            raise ValueError(
                f"此交易狀態為 {payment_request.status}，無法取消"
            )

        # 【新增】先通知 Bank Mock，失敗會拋例外，本地不寫 DB
        self.ecpay_gateway.cancel_account(merchant_trade_no)

        with transaction.atomic():

            # 【新增】同步 ecpay_mock Order.status（若有建立）
            gateway_order = (
                Order.objects
                .select_for_update()
                .filter(order_number=merchant_trade_no)
                .first()
            )

            if gateway_order:
                gateway_order.status = "cancelled"
                gateway_order.save(
                    update_fields=["status", "updated_at"]
                )

            # 【新增】PaymentRequest 改為 atm_cancelled
            payment_request.status = "atm_cancelled"
            payment_request.save(update_fields=["status"])

        return {
            "status": True,
            "merchant_trade_no": merchant_trade_no,
            "payment_status": "atm_cancelled",
        }

    # ============================================================
    # 【新增】
    # Payment Notification 日期處理
    # ============================================================

    def _get_payment_date(
        self,
        request_data: Dict[str, Any],
    ) -> datetime:
        """
        【新增】

        取得 Bank Mock callback 的 payment_date。
        """

        value = (
            request_data.get(
                "payment_date"
            )
            or request_data.get(
                "PaymentDate"
            )
        )

        if value is None:

            return timezone.now()

        if isinstance(
            value,
            datetime,
        ):

            if timezone.is_naive(
                value
            ):
                return timezone.make_aware(
                    value
                )

            return value

        try:

            result = datetime.fromisoformat(
                str(value)
            )

            if timezone.is_naive(
                result
            ):

                result = timezone.make_aware(
                    result
                )

            return result

        except ValueError as exc:

            raise ValueError(
                "payment_date 格式錯誤"
            ) from exc

    # ========================================================
    # ATM 建立
    # ========================================================

    def create_atm_payment(
        self,
        *,
        request_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        【修改】

        建立 ECPay Mock ATM Payment。

        ========================================================
        第一階段
        ========================================================

        接收：

            E_commerce
                ↓
            ecpay_gateway_checkout/

        ========================================================
        第二階段
        ========================================================

        呼叫：

            ECPayMockAdapter
                ↓
            Bank Mock

        ========================================================
        第三階段
        ========================================================

        Bank Mock 回傳：

            bank_code
            v_account
            expire_date

        ========================================================
        第四階段
        ========================================================

        ECPayService：

            產生 trade_no
            ↓
            建立 PaymentRequest
            ↓
            回傳 ATM 資訊
        """

        try:
            # ==================================================
            # 【新增】
            # 基本輸入驗證
            # ==================================================

            if not isinstance(
                request_data,
                dict,
            ):
                raise ValueError(
                    "request_data 必須是 dict"
                )

            merchant_trade_no = (
                request_data.get(
                    "merchant_trade_no"
                )
            )

            trade_amt = (
                request_data.get(
                    "trade_amt"
                )
            )

            item_name = (
                request_data.get(
                    "item_name"
                )
                or "購買商品"
            )

            choose_payment = (
                request_data.get(
                    "choose_payment"
                )
                or "ATM"
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

            if choose_payment != "ATM":
                raise ValueError(
                    "目前 ECPay Mock 僅支援 ATM"
                )

            merchant_trade_no = str(
                merchant_trade_no
            )

            # ==================================================
            # 【保留】
            # 金額格式驗證
            # ==================================================

            try:

#                amount = Decimal(
#                    str(trade_amt)
#                )
                # 先轉成浮點數再轉成整數（或先轉 Decimal 再轉 int）
                amount = int(Decimal(str(trade_amt)))

            except (
                TypeError,
                ValueError,
            ) as exc:

                raise ValueError(
                    "trade_amt 格式錯誤"
                ) from exc

            if amount <= 0:
                raise ValueError(
                    "trade_amt 必須大於 0"
                )

            # ==================================================
            # 【修改】
            #
            # Service 不直接使用 ORM。
            #
            # 透過 Repository 查詢是否已有資料。
            # ==================================================

            # try:
            #     existing_payment = (
            #         self.repository
            #         .get_by_merchant_trade_no(
            #             merchant_trade_no
            #         )
            #     )
            # 
            # except Exception as exc:
            #     logger.exception(
            #         "查詢既有 PaymentRequest 失敗"
            #     )
            # 
            #     raise RuntimeError(
            #         "PaymentRequest 查詢失敗"
            #     ) from exc

            try:
                existing_payment = (
                    PaymentRequest.objects
                    .filter(
                        merchant_trade_no=merchant_trade_no
                    )
                    .first()
                )

            except Exception as exc:
                logger.exception(
                    "查詢既有 PaymentRequest 失敗"
                )

                raise RuntimeError(
                    "PaymentRequest 查詢失敗"
                ) from exc

            if existing_payment is not None:

                logger.info(
                    "PaymentRequest 已存在，"
                    "準備重新確認 Store Payment："
                    "merchant_trade_no=%s",
                    merchant_trade_no,
                )

                # ==================================================
                # 【新增】
                # 即使 PaymentRequest 已存在，
                # 仍重新通知 Store。
                #
                # Store callback 本身具有 idempotent 行為：
                #
                # 第一次：
                #     Payment.objects.create()
                #
                # 第二次：
                #     找到既有 Payment → update
                #
                # 因此可以安全重送。
                # ==================================================

                existing_response = (
                    self._build_atm_response(
                        existing_payment
                    )
                )

                existing_payment_data = (
                    existing_response[
                        "payment"
                    ]
                )

                store_callback_payload = {

                    "merchant_trade_no": (
                        existing_payment
                        .merchant_trade_no
                    ),

                    "trade_no": str(
                        existing_payment.trade_no
                    ),

                    "provider_transaction_id": str(
                        existing_payment.trade_no
                    ),

                    "trade_amt": str(
                        existing_payment.trade_amt
                    ),

                    "status": "atm_created",

                    "payment_status": "atm_created",

                    "rtn_code": 0,

                    "rtn_msg": (
                        "ATM 付款資訊已存在"
                    ),

                    "choose_payment": (
                        existing_payment.choose_payment
                    ),

                    "payment_type": (
                        existing_payment.payment_type
                    ),

                    "payment_date": (
                        timezone.now().isoformat()
                    ),

                    "bank_code": str(
                        existing_payment.bank_code
                    ),

                    "v_account": str(
                        existing_payment.v_account
                    ),

                    "expire_date": (
                        existing_payment
                        .expire_date
                        .isoformat()
                    ),

                    "atm_info_url": (
                        existing_response[
                            "atm_info_url"
                        ]
                    ),
                }

                store_callback_result = (
                    self._notify_store_payment_result(
                        store_callback_payload
                    )
                )

                # 【新增】重送時若 Order 還沒建（舊資料），一併補建
                self._ensure_gateway_order(
                    request_data,
                    merchant_trade_no,
                    amount,
                )

                existing_response[
                    "store_callback"
                ] = store_callback_result

                return existing_response

            # ==================================================
            # 【修改】
            #
            # 建立送往 Bank Mock 的業務 payload。
            #
            # Store → Ecpay Mock 原始 CheckMacValue
            # 不直接沿用到 Bank Mock。
            #
            # Adapter 會重新產生：
            #
            # Ecpay Mock → Bank Mock
            # 的 CheckMacValue
            # ==================================================

            gateway_payload = {
                "merchant_trade_no": (
                    merchant_trade_no
                ),
                "trade_amt": str(
                    amount
                ),
                "item_name": str(
                    item_name
                ),
                "choose_payment": "ATM",
            }

            # ==================================================
            # 【保留】
            #
            # Adapter 負責 HTTPX。
            # Service 不碰 HTTPX。
            # ==================================================

            try:

                atm_result = (
                    self.ecpay_gateway
                    .create_atm_payment(
                        gateway_payload
                    )
                )

            except ValueError:
                raise

            except RuntimeError:
                raise

            except Exception as exc:

                logger.exception(
                    "ECPay Gateway / Bank Mock 呼叫失敗"
                )

                raise RuntimeError(
                    "ATM 付款建立失敗"
                ) from exc

            # ==================================================
            # 【修改】
            #
            # Adapter 回傳 dict。
            # 不再使用錯誤的 dataclass attribute。
            # ==================================================

            if not isinstance(
                atm_result,
                dict,
            ):
                raise RuntimeError(
                    "ECPay Gateway 回傳格式錯誤"
                )

            if not atm_result.get(
                "success"
            ):
                raise RuntimeError(
                    "Bank Mock ATM 建立失敗"
                )

            response_merchant_trade_no = (
                atm_result.get(
                    "merchant_trade_no"
                )
            )

            if not response_merchant_trade_no:
                raise RuntimeError(
                    "Gateway 回應缺少 merchant_trade_no"
                )

            if (
                str(response_merchant_trade_no)
                != merchant_trade_no
            ):
                raise RuntimeError(
                    "Gateway merchant_trade_no 不一致"
                )

            # ==================================================
            # 【保留】
            #
            # 這三個值只能相信 Bank Mock 回傳的資料。
            # ==================================================

            bank_code = atm_result.get(
                "bank_code"
            )

            v_account = atm_result.get(
                "v_account"
            )

            expire_date = atm_result.get(
                "expire_date"
            )

            payment_status = (
                atm_result.get(
                    "payment_status"
                )
                or "pending"
            )

            if not bank_code:
                raise RuntimeError(
                    "缺少 bank_code"
                )

            if not v_account:
                raise RuntimeError(
                    "缺少 v_account"
                )

            if not expire_date:
                raise RuntimeError(
                    "缺少 expire_date"
                )

            # ==================================================
            # 【新增】
            # expire_date 統一為 aware datetime
            # ==================================================

            expire_datetime = (
                self._normalize_expire_date(
                    expire_date
                )
            )

            if (
                expire_datetime
                <= timezone.now()
            ):

                raise ValueError(
                    "ATM 付款期限必須晚於目前時間"
                )

            # ==================================================
            # 【保留】
            #
            # ECPay Mock 自己產生 trade_no。
            #
            # 這不是 Bank Mock 產生的。
            # ==================================================

            trade_no = (
                "EC"
                + uuid.uuid4()
                .hex[:18]
                .upper()
            )

            # ==================================================
            # 【保留】
            #
            # Store → Ecpay Mock 的原始
            # CheckMacValue 可以保存到 PaymentRequest，
            # 但不拿它直接送給 Bank Mock。
            # ==================================================

            incoming_check_mac = (
                request_data.get(
                    "CheckMacValue"
                )
            )

            # ==================================================
            # 【修改】
            #
            # ORM 不在 Service。
            # 透過 Repository 建立。
            # ==================================================

            payment_data = {
                "merchant_id": request_data.get(
                    "merchant_id",
                    "2000132",
                ),
                "merchant_trade_no": (
                    merchant_trade_no
                ),
                "merchant_trade_date": (
                    self._get_trade_date(
                        request_data
                    )
                ),
                "trade_amt": amount,
                "trade_desc": request_data.get(
                    "trade_desc",
                    "購買商品",
                ),
                "item_name": str(
                    item_name
                ),
                "payment_type": request_data.get(
                    "payment_type",
                    "aio",
                ),
                "choose_payment": "ATM",
                "trade_no": trade_no,
                "bank_code": str(
                    bank_code
                ),
                "v_account": str(
                    v_account
                ),
                "expire_date": (
                    expire_datetime
                ),
                # ------------------------------------------------
                # 【保留】
                #
                # ECPay Mock 自己的 PaymentRequest 狀態，
                # 不是 Store Order.status。
                # ------------------------------------------------

                "status": "atm_created",

                "check_mac_value": (
                    incoming_check_mac
                ),

                "return_url": request_data.get(
                    "ReturnURL"
                ),

                "payment_info_url": request_data.get(
                    "PaymentInfoURL"
                ),

                "order_result_url": request_data.get(
                    "OrderResultURL"
                ),
            }

            try:

                # payment_request = (
                #     self.repository
                #     .create_payment_request(
                #         payment_data
                #     )
                # )

                # payment_request = PaymentRequest.objects.create(
                    # **payment_data
                # )

                # 【修改】原本 PaymentRequest.objects.create(**payment_data)
                # 改成未存檔物件，商店通知成功後才 save()
                payment_request = PaymentRequest(
                    **payment_data
                )
                
            except Exception as exc:

                logger.exception(
                    "PaymentRequest 建立失敗"
                )

                raise RuntimeError(
                    "ECPay ATM PaymentRequest 建立失敗"
                ) from exc

            # ==================================================
            # 【修改】
            #
            # ATM 建立成功後，
            # 先通知 E_commerce。
            #
            # 這個時機非常重要：
            #
            # Bank Mock
            #     ↓
            # ATM 資訊完成
            #     ↓
            # PaymentRequest 建立完成
            #     ↓
            # StorePaymentGateway
            #     ↓
            # Store Payment 建立
            #
            # 此時 Store Payment 第一次建立。
            # ==================================================

            atm_response = (
                self._build_atm_response(
                    payment_request
                )
            )

            atm_payment = (
                atm_response.get(
                    "payment",
                    {},
                )
            )

            store_callback_payload = {

                "merchant_trade_no": (
                    payment_request
                    .merchant_trade_no
                ),

                # ------------------------------------------------
                # 【新增】
                # ECPay Mock trade_no。
                # ------------------------------------------------

                "trade_no": str(
                    payment_request.trade_no
                ),

                # ------------------------------------------------
                # 【新增】
                # 明確提供 Store：
                # provider_transaction_id
                # ------------------------------------------------

                "provider_transaction_id": str(
                    payment_request.trade_no
                ),

                "trade_amt": str(
                    payment_request.trade_amt
                ),

                # ------------------------------------------------
                # 【新增】
                # ATM 建立階段不是 paid。
                #
                # Store PaymentService 的 STATUS_MAP：
                #
                # atm_created → pending
                # ------------------------------------------------

                "status": "atm_created",

                "payment_status": "atm_created",

                "rtn_code": 0,

                "rtn_msg": (
                    "ATM 付款資訊建立成功"
                ),

                "choose_payment": (
                    payment_request.choose_payment
                ),

                "payment_type": (
                    payment_request.payment_type
                ),

                "payment_date": (
                    timezone.now().isoformat()
                ),

                "bank_code": str(
                    payment_request.bank_code
                ),

                "v_account": str(
                    payment_request.v_account
                ),

                "expire_date": (
                    payment_request
                    .expire_date
                    .isoformat()
                ),

                "atm_info_url": (
                    atm_response[
                        "atm_info_url"
                    ]
                ),
            }

            # ==================================================
            # 【新增】
            # Ecpay Mock → E_commerce
            #
            # StorePaymentAdapter 會：
            #
            #     重新產生 CheckMacValue
            #     ↓
            #     HTTPX
            #     ↓
            #     Store /atm_payment_notify/
            #
            # ECPayService 不使用 HTTPX。
            # ==================================================

            store_callback_result = (
                self._notify_store_payment_result(
                    store_callback_payload
                )
            )
            
            # 【新增】商店通知成功後，才寫入 8001 DB
            # （商店失敗會在上一步丟例外，不會執行到這裡）
            payment_request.save()

            # 【新增】ATM 流程同步建立 ecpay_mock Order（原本只有 COD 會建）
            self._ensure_gateway_order(
                request_data,
                merchant_trade_no,
                amount,
            )
            
            logger.info(
                "ECPay ATM 建立完成並已通知 Store："
                "merchant_trade_no=%s, "
                "trade_no=%s, "
                "bank_code=%s",
                merchant_trade_no,
                trade_no,
                bank_code,
            )

            # ==================================================
            # 【修改】
            #
            # 把 Store callback 結果一起保留下來，
            # 方便 View 判斷 Store Payment 是否真的建立成功。
            # ==================================================

            atm_response[
                "store_callback"
            ] = store_callback_result

            return atm_response

        except ValueError:
            raise

        except RuntimeError:
            raise

        except Exception as exc:

            logger.exception(
                "ECPayService.create_atm_payment "
                "發生未預期錯誤"
            )

            raise RuntimeError(
                "ATM 付款建立失敗"
            ) from exc

    # ========================================================
    # 【新增】建立 / 取得 ecpay_mock 自己的 Order 紀錄
    #
    # 與 COD（cod_service.confirm_store）一致：
    # 用 order_number 做 get_or_create，重送不會重複建立。
    # 缺少 user_id（舊版 payload）時只記 warning，不中斷 ATM 流程。
    # ========================================================
    def _ensure_gateway_order(
        self,
        request_data: Dict[str, Any],
        merchant_trade_no: str,
        amount,
    ):
        user_id = request_data.get("user_id")

        if user_id in (None, ""):
            logger.warning(
                "ATM 缺少 user_id，略過建立 ecpay_mock Order："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )
            return None

        order_obj, created = Order.objects.get_or_create(
            order_number=merchant_trade_no,
            defaults={
                "user_id": int(user_id),
                "receiver_name": str(
                    request_data.get("receiver_name") or ""
                ),
                "amount": amount,
                "status": "pending",
            },
        )

        logger.info(
            "ecpay_mock Order %s：merchant_trade_no=%s",
            "建立成功" if created else "已存在",
            merchant_trade_no,
        )

        return order_obj

    # ========================================================
    # expire_date
    # ========================================================

    def _normalize_expire_date(
        self,
        expire_date: Any,
    ) -> datetime:
        """
        【新增】

        將 Bank Mock 回傳的 expire_date
        統一轉成 aware datetime。
        """

        if isinstance(
            expire_date,
            datetime,
        ):

            result = expire_date

        elif isinstance(
            expire_date,
            str,
        ):

            try:

                result = datetime.fromisoformat(
                    expire_date
                )

            except ValueError as exc:

                raise ValueError(
                    "expire_date 格式錯誤"
                ) from exc

        else:

            raise ValueError(
                "expire_date 格式錯誤"
            )

        if timezone.is_naive(
            result
        ):
            result = timezone.make_aware(
                result
            )

        return result

    # ========================================================
    # merchant_trade_date
    # ========================================================

    def _get_trade_date(
        self,
        request_data: Dict[str, Any],
    ) -> datetime:
        """
        【保留】

        取得 merchant_trade_date。
        """

        value = request_data.get(
            "merchant_trade_date"
        )

        if value is None:
            return timezone.now()

        if isinstance(
            value,
            datetime,
        ):

            if timezone.is_naive(
                value
            ):
                return timezone.make_aware(
                    value
                )

            return value

        try:

            result = datetime.fromisoformat(
                str(value)
            )

            if timezone.is_naive(
                result
            ):
                result = timezone.make_aware(
                    result
                )

            return result

        except ValueError:

            logger.warning(
                "merchant_trade_date 格式錯誤，"
                "改用目前時間"
            )

            return timezone.now()

    # ========================================================
    # ATM Response
    # ========================================================

    def _build_atm_response(
        self,
        payment_request: PaymentRequest,
    ) -> Dict[str, Any]:
        """
        【修改】

        整理最後回傳給 E_commerce 的 ATM Response。
        """

        try:

            if payment_request is None:
                raise RuntimeError(
                    "PaymentRequest 不存在"
                )

            expire_date = getattr(
                payment_request,
                "expire_date",
                None,
            )

            if expire_date is not None:

                try:

                    expire_date = (
                        expire_date.isoformat()
                    )

                except AttributeError:

                    expire_date = str(
                        expire_date
                    )

            # ==================================================
            # 【新增】
            # ATM 資訊頁 URL
            #
            # 注意：
            #
            # merchant_trade_no 是 Store 的：
            #
            #     ORD-xxxxxxxxxxxx
            #
            # 不是 ECPay trade_no：
            #
            #     ECxxxxxxxxxxxxxxxxxx
            # ==================================================

            ecpay_mock_base_url = (
                getattr(
                    settings,
                    "HF_SPACE_ECPAY_MOCK_URL",
                    "",
                )
                or ""
            ).rstrip("/")

            atm_info_url = (
                f"{ecpay_mock_base_url}"
                "/gateway/atm_info/"
                f"?merchant_trade_no="
                f"{payment_request.merchant_trade_no}"
            )

            return {
                "status": True,

                "message": (
                    "ATM 付款建立成功"
                ),

                # ==================================================
                # 【新增】
                # Browser 最後要前往的 ATM 資訊頁。
                # ==================================================

                "atm_info_url": (
                    atm_info_url
                ),

                "payment": {
                    "merchant_trade_no": str(
                        payment_request
                        .merchant_trade_no
                    ),

                    "trade_no": str(
                        payment_request.trade_no
                    ),

                    "bank_code": str(
                        payment_request.bank_code
                    ),

                    "v_account": str(
                        payment_request.v_account
                    ),

                    "expire_date": (
                        expire_date
                    ),

                    "status": str(
                        payment_request.status
                    ),

                    "check_mac_value": getattr(
                        payment_request,
                        "check_mac_value",
                        None,
                    ),
                },
            }

        except RuntimeError:
            raise

        except Exception as exc:

            logger.exception(
                "ATM Response 整理失敗"
            )

            raise RuntimeError(
                "ATM Response 整理失敗"
            ) from exc