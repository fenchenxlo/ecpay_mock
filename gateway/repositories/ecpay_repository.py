# ============================================================
# ECPay Mock
# gateway/repositories/ecpay_repository.py
# ============================================================

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from django.db import IntegrityError, transaction

from ..models import (
    PaymentNotification,
    PaymentRequest,
)


logger = logging.getLogger(__name__)


class ECPayRepository:
    """
    【修改】

    ECPay Mock DB Repository。

    ============================================================
    唯一 ORM 責任
    ============================================================

    PaymentRequest
    PaymentNotification

    Service 不直接使用 Django ORM。
    """

    # ========================================================
    # PaymentRequest 查詢
    # ========================================================

    def get_by_merchant_trade_no(
        self,
        merchant_trade_no: str,
    ) -> Optional[PaymentRequest]:
        """
        【保留】
        """

        try:

            return (
                PaymentRequest.objects
                .filter(
                    merchant_trade_no=str(
                        merchant_trade_no
                    )
                )
                .first()
            )

        except Exception as exc:

            logger.exception(
                "查詢 PaymentRequest 失敗: "
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise RuntimeError(
                "PaymentRequest 查詢失敗"
            ) from exc

    # ========================================================
    # PaymentRequest 建立
    # ========================================================

    def create_payment_request(
        self,
        data: Dict[str, Any],
    ) -> PaymentRequest:
        """
        【保留】
        """

        if not isinstance(
            data,
            dict,
        ):
            raise ValueError(
                "PaymentRequest data 必須是 dict"
            )

        if not data.get(
            "merchant_trade_no"
        ):
            raise ValueError(
                "缺少 merchant_trade_no"
            )

        try:

            with transaction.atomic():

                return PaymentRequest.objects.create(
                    **data
                )

        except IntegrityError as exc:

            logger.warning(
                "PaymentRequest 建立發生 IntegrityError，"
                "嘗試取得既有資料: merchant_trade_no=%s",
                data.get(
                    "merchant_trade_no"
                ),
            )

            try:

                existing = (
                    self.get_by_merchant_trade_no(
                        data[
                            "merchant_trade_no"
                        ]
                    )
                )

            except Exception as lookup_exc:

                logger.exception(
                    "IntegrityError 後重新查詢 PaymentRequest 失敗"
                )

                raise RuntimeError(
                    "PaymentRequest 建立失敗"
                ) from lookup_exc

            if existing is not None:
                return existing

            raise RuntimeError(
                "PaymentRequest 建立失敗"
            ) from exc

        except Exception as exc:

            logger.exception(
                "PaymentRequest ORM 建立失敗"
            )

            raise RuntimeError(
                "PaymentRequest 建立失敗"
            ) from exc

    # ========================================================
    # 【新增】
    # PaymentRequest 更新
    # ========================================================

    def update_payment_request(
        self,
        payment_request: PaymentRequest,
        data: Dict[str, Any],
    ) -> PaymentRequest:
        """
        【新增】

        更新既有 PaymentRequest。

        ORM 仍然只放在 Repository。
        """

        if payment_request is None:

            raise ValueError(
                "PaymentRequest 不存在"
            )

        if not isinstance(
            data,
            dict,
        ):

            raise ValueError(
                "PaymentRequest update data 必須是 dict"
            )

        try:

            with transaction.atomic():

                for field, value in data.items():

                    setattr(
                        payment_request,
                        field,
                        value,
                    )

                payment_request.save(
                    update_fields=list(
                        data.keys()
                    )
                    + ["updated_at"]
                    if hasattr(
                        payment_request,
                        "updated_at",
                    )
                    else list(
                        data.keys()
                    )
                )

            return payment_request

        except Exception as exc:

            logger.exception(
                "PaymentRequest 更新失敗: "
                "merchant_trade_no=%s",
                getattr(
                    payment_request,
                    "merchant_trade_no",
                    None,
                ),
            )

            raise RuntimeError(
                "PaymentRequest 更新失敗"
            ) from exc

    # ========================================================
    # 【新增】
    # PaymentNotification 建立
    # ========================================================

    def create_payment_notification(
        self,
        data: Dict[str, Any],
    ) -> PaymentNotification:
        """
        【新增】

        建立 ECPay Mock PaymentNotification。

        ORM 只在 Repository。
        """

        if not isinstance(
            data,
            dict,
        ):

            raise ValueError(
                "PaymentNotification data 必須是 dict"
            )

        required_fields = (
            "merchant_trade_no",
            "trade_no",
            "trade_amt",
            "payment_date",
            "choose_payment",
            "payment_type",
            "rtn_code",
            "rtn_msg",
        )

        for field in required_fields:

            if data.get(field) in (
                None,
                "",
            ):

                raise ValueError(
                    f"PaymentNotification 缺少 {field}"
                )

        try:

            with transaction.atomic():

                return (
                    PaymentNotification.objects.create(
                        **data
                    )
                )

        except Exception as exc:

            logger.exception(
                "PaymentNotification 建立失敗: "
                "merchant_trade_no=%s",
                data.get(
                    "merchant_trade_no"
                ),
            )

            raise RuntimeError(
                "PaymentNotification 建立失敗"
            ) from exc