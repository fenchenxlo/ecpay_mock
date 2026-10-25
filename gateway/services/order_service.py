# commerce_shop/services/order_service.py

import uuid
import logging
from django.db import transaction

from commerce_shop.models import Order

from commerce_shop.services.payment_service import (
    PaymentService,
)

logger = logging.getLogger(__name__)

class OrderService:
    """
    Order Service

    負責 Checkout 的第一階段：

        1. 建立 Order
        2. 呼叫 PaymentService
        3. 建立 PaymentRequest
        4. 回傳 Checkout 結果

    注意：

        OrderService 不直接呼叫 ECPay。

        正確架構：

            OrderService
                  ↓
            PaymentService
                  ↓
            ECPayGateway
                  ↓
            ECPayMockAdapter
    """

    def __init__(
        self,
        payment_service: PaymentService,
    ):
        self.payment_service = payment_service

    # ========================================================
    # Checkout
    # ========================================================

    @transaction.atomic
    def checkout(
        self,
        *,
        user_id: int,
        receiver_name: str,
        amount,
        item_name: str,
        choose_payment: str,
    ):
        """
        建立訂單並建立付款請求。

        整個流程使用 transaction.atomic。

        如果 PaymentRequest 建立失敗：

            Order

        也會 rollback。

        避免只產生一筆沒有付款資訊的訂單。
        """

        # ----------------------------------------------------
        # 產生商店訂單編號
        #
        # 使用 ORDER + UUID
        #
        # 例如：
        #
        # ORDER20260910A1B2C3D4
        # ----------------------------------------------------

        order_number = (
            "ORDER"
            + uuid.uuid4().hex[:20].upper()
        )

        # ----------------------------------------------------
        # 第一次核心功能：
        #
        # 建立 Order
        # ----------------------------------------------------

        try:
            # 【新增】
            #
            # 這裡預留 ECPay Mock 自己的 Order 建立位置。
            #
            # 取得實際 models.py 後：
            #
            # order = Order.objects.create(...)
            #
            # 再交給 PaymentService。
            #
            order = None

        except Exception as ex:
            logger.exception(
                "ECPay Mock Order 建立失敗"
            )
            raise RuntimeError(
                "ECPay Mock Order 建立失敗"
            ) from ex
        # )   # 【修改】多餘的右括號造成 SyntaxError,改為註解

        # ----------------------------------------------------
        # 【新增】
        #
        # 如果目前 ECPay Mock checkout 並沒有自己的
        # Order 建立需求，而只是 Payment Gateway，
        # 則不應該在這裡虛構 Order ORM。
        #
        # 因此目前先直接要求呼叫端使用
        # PaymentService 建立 ATM。
        # ----------------------------------------------------

        if order is None:
            raise RuntimeError(
                "ECPay Mock Order Model 尚未接入 OrderService"
            )

        try:
            payment_request = (
                self.payment_service.create_payment(
                    order=order,
                    item_name=item_name,
                    choose_payment=choose_payment,
                )
            )

        except ValueError:
            raise

        except Exception as ex:
            logger.exception(
                "ECPay Mock PaymentService 執行失敗"
            )
            raise RuntimeError(
                "ECPay Mock 付款建立失敗"
            ) from ex

        result = {
            # 【保留】
            "order": order,
            "payment_request": payment_request,
        }

        if payment_request:
            result["payment"] = {
                # 【保留】
                "merchant_trade_no":
                    payment_request.merchant_trade_no,

                "trade_no":
                    payment_request.trade_no,

                "bank_code":
                    payment_request.bank_code,

                "v_account":
                    payment_request.v_account,

                "expire_date":
                    payment_request.expire_date,

                "status":
                    payment_request.status,
            }

        else:
            result["payment"] = {
                # 【保留】
                "choose_payment": "COD",
                "status": "pending",
            }

        return result