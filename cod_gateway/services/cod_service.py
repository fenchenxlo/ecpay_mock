# ============================================================
# 【新增】COD Service
# Service 負責：業務驗證 + ORM
# Service 不使用 httpx、不計算 CheckMacValue（交給 Adapter）
# 原則：先通知商店，成功才寫 ecpay_mock DB
# ============================================================

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict
import uuid   # 【新增】產生 trade_no

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from gateway.models import Order  # 共用 model，不修改 gateway app

from ..adapters.cod_store_adapter import CODStoreAdapter
from ..models import CODPaymentRequest

logger = logging.getLogger(__name__)


class CODService:

    REQUIRED_FIELDS = (
        "merchant_trade_no",
        "merchant_trade_date",
        "user_id",
        "trade_amt",
    )

    # 後台按鈕 action → CODPaymentRequest.status（同時也是送給商店的 status）
    ACTIONS = {
        "created": "cod_created",
        "shipped": "cod_shipped",
        "paid": "cod_paid",
        "failed": "cod_failed",
        "expired": "cod_expired",   # 【新增】模擬逾期未付款
    }

    def __init__(self, store_gateway=None):
        self.store_gateway = store_gateway or CODStoreAdapter()

    # --------------------------------------------------------
    # 【新增】產生 ECPay trade_no，格式與 ATM 相同：EC + 18 碼大寫
    # --------------------------------------------------------
    @staticmethod
    def _new_trade_no():
        return "EC" + uuid.uuid4().hex[:18].upper()

    # --------------------------------------------------------
    # merchant_trade_date：同時支援 "-" 與 "/"
    # --------------------------------------------------------
    @staticmethod
    def _parse_trade_date(raw):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
            try:
                value = datetime.strptime(str(raw), fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError("merchant_trade_date 格式錯誤")

        if settings.USE_TZ and timezone.is_naive(value):
            value = timezone.make_aware(value)
        return value

    # --------------------------------------------------------
    # 通知商店（Adapter 簽章 + httpx），失敗就丟例外
    # --------------------------------------------------------
    def _notify_store(
        self,
        *,
        merchant_trade_no,
        trade_amt,
        status,
        trade_no,          # 【新增】
        store_name="",
        store_address="",
        logistics_subtype="",
        simulate=False,    # 【新增】True=來自後台模擬頁
    ):
        payload = {
            "merchant_trade_no": merchant_trade_no,
            "trade_amt": str(int(Decimal(str(trade_amt)))),
            "status": status,
            "payment_method": "COD",
#            "provider_transaction_id": f"COD-{merchant_trade_no}",
            # 【修改】原本 f"COD-{merchant_trade_no}"
            "provider_transaction_id": trade_no,
#            "trade_no": f"COD-{merchant_trade_no}",
            "trade_no": trade_no,
            "cvs_store_name": store_name or "",
            "cvs_store_address": store_address or "",
            "logistics_subtype": logistics_subtype or "",
            "payment_date": timezone.now().isoformat(),
        }

        # 【新增】模擬頁標記；Adapter 會把它一起簽進 CheckMacValue，商店端才能信任
        if simulate:
            payload["simulate"] = "1"

        result = self.store_gateway.notify_cod_status(payload)
        res_data = result["response_data"]
        logger.info(f"res_data={dict(res_data)}")

        if not isinstance(result, dict) or not result.get("success"):
            message = (
                result.get("message") if isinstance(result, dict) else result
            )
            raise RuntimeError(f"商店處理失敗：{message}")

        return result

    # --------------------------------------------------------
    # 第一站：驗證商店送來的資料，整理成 session 可存的 dict（不寫 DB）
    # --------------------------------------------------------
    def prepare_checkout(self, payment_data: Dict[str, Any]) -> Dict[str, str]:

        missing = [
            k for k in self.REQUIRED_FIELDS if not payment_data.get(k)
        ]
        if missing:
            raise ValueError(f"缺少欄位: {', '.join(missing)}")

        try:
            amount = Decimal(str(payment_data["trade_amt"]))
        except InvalidOperation as exc:
            raise ValueError("trade_amt 格式錯誤") from exc

        if amount <= 0:
            raise ValueError("trade_amt 必須大於 0")

        self._parse_trade_date(payment_data["merchant_trade_date"])

        return {
            "merchant_trade_no": str(payment_data["merchant_trade_no"]),
            "merchant_trade_date": str(payment_data["merchant_trade_date"]),
            "user_id": str(payment_data["user_id"]),
            "trade_amt": str(payment_data["trade_amt"]),
            "item_name": str(payment_data.get("item_name", "")),
            "receiver_name": str(payment_data.get("receiver_name", "") or "王大明"),
            "receiver_cell_phone": str(payment_data.get("receiver_cell_phone", "")),
            "receiver_address": str(payment_data.get("receiver_address", "")),
            "return_url": str(payment_data.get("ReturnURL", "")),
            "order_result_url": str(payment_data.get("OrderResultURL", "")),
        }

    # --------------------------------------------------------
    # 第二站：確認門市。先通知商店，成功才寫 ecpay DB
    # --------------------------------------------------------
    def confirm_store(
        self,
        *,
        checkout_data: Dict[str, str],
        store: Dict[str, Any],
    ) -> CODPaymentRequest:

        if not checkout_data:
            raise ValueError("找不到結帳資料（session 已遺失），請重新從商城結帳")

        merchant_trade_no = checkout_data["merchant_trade_no"]

        # 【新增】已存在就沿用（重送不會產生新編號），否則新產生
        existing = CODPaymentRequest.objects.filter(
            merchant_trade_no=merchant_trade_no
        ).first()
        trade_no = (
            existing.trade_no
            if existing and existing.trade_no
            else self._new_trade_no()
        )

        # 1. 先通知商店（失敗會丟 RuntimeError，下面的 DB 不會執行）
        self._notify_store(
            merchant_trade_no=merchant_trade_no,
            trade_amt=checkout_data["trade_amt"],
            status="cod_confirmed",
            trade_no=trade_no,          # 【新增】
            store_name=store["name"],
            store_address=store["address"],
            logistics_subtype=store["chain"],
        )

        # 2. 商店成功後才寫 ecpay DB
        with transaction.atomic():
            order_obj, _ = Order.objects.get_or_create(
                order_number=merchant_trade_no,
                defaults={
                    "user_id": int(checkout_data["user_id"]),
                    "receiver_name": checkout_data["receiver_name"],
                    "amount": checkout_data["trade_amt"],
                    "status": "pending",
                },
            )

            cod_payment, _ = CODPaymentRequest.objects.update_or_create(
                merchant_trade_no=merchant_trade_no,
                defaults={
                    "order": order_obj,
                    "merchant_trade_date": self._parse_trade_date(
                        checkout_data["merchant_trade_date"],                    
                    ),
                    "trade_no": trade_no,   # 【新增】商店成功後才寫入
                    "trade_amt": checkout_data["trade_amt"],
                    "item_name": checkout_data["item_name"],
                    "receiver_name": checkout_data["receiver_name"],
                    "receiver_cell_phone": checkout_data["receiver_cell_phone"],
                    "receiver_address": checkout_data["receiver_address"],
                    "status": "cod_created",
                    "check_mac_value": checkout_data.get("check_mac_value", ""),
                    "return_url": checkout_data["return_url"],
                    "order_result_url": checkout_data["order_result_url"],
                    "logistics_subtype": store["chain"],
                    "store_id": store["store_id"],
                    "store_name": store["name"],
                    "store_address": store["address"],
                    "store_lat": store["lat"],
                    "store_lng": store["lng"],
                },
            )

        return cod_payment

    # --------------------------------------------------------
    # 後台模擬：created / shipped / paid / failed
    # 先通知商店，成功才更新 ecpay DB
    # --------------------------------------------------------
    # --------------------------------------------------------
    # 【新增】商城端取消訂單（E_commerce → ecpay_mock）
    # COD 不經過 Bank，ecpay_mock 是鏈路末端，直接寫自己的 DB。
    # 【重點】只有 cod_created（待出貨）/ cod_failed（取貨失敗）可取消；
    #         已配送 / 已取貨付款 / 已逾期都不可取消。
    # --------------------------------------------------------
    def cancel(self, merchant_trade_no: str, delete_record: bool = False) -> Dict[str, Any]:

        with transaction.atomic():
            cod = CODPaymentRequest.objects.select_for_update().filter(
                merchant_trade_no=merchant_trade_no
            ).first()

            # 【新增】刪除模式（商店刪除訂單）：COD 是鏈尾，沒有下游，直接刪。
            # 找不到視為成功；必須已是 cod_cancelled，避免誤刪仍有效的訂單。
            # 刪 gateway.Order 會 CASCADE 帶走 CODPaymentRequest
            if delete_record:
                if cod is not None:
                    if cod.status != "cod_cancelled":
                        raise ValueError(
                            f"此訂單狀態為「{cod.get_status_display()}」，請先取消訂單再刪除"
                        )
                    cod.order.delete()
                return {
                    "status": True,
                    "merchant_trade_no": merchant_trade_no,
                    "cod_status": "deleted",
                }

            # 尚未選門市：ecpay_mock 沒有 COD 紀錄，沒有東西需要取消
            if cod is None:
                return {
                    "status": True,
                    "merchant_trade_no": merchant_trade_no,
                    "cod_status": "none",
                }

            # 【重點】在鎖內判斷狀態，避免與模擬頁同時操作
            if cod.status in ("cod_shipped", "cod_paid", "cod_expired"):
                raise ValueError(
                    f"此訂單狀態為「{cod.get_status_display()}」，無法取消"
                )

            cod.status = "cod_cancelled"
            cod.save(update_fields=["status", "updated_at"])

            # 共用 gateway.Order 同步為 cancelled（choices 已有此選項）
            order = cod.order
            order.status = "cancelled"
            order.save()

        return {
            "status": True,
            "merchant_trade_no": merchant_trade_no,
            "cod_status": "cod_cancelled",
        }

    def simulate(self, merchant_trade_no: str, action: str) -> Dict[str, Any]:

        if action not in self.ACTIONS:
            raise ValueError(f"未知的操作：{action}")

        target_status = self.ACTIONS[action]
        logger.info(f"action={action}")
        logger.info(f"target_status={target_status}")
        
        cod = CODPaymentRequest.objects.filter(
            merchant_trade_no=merchant_trade_no
        ).first()

        if cod is None:
            raise LookupError("找不到該筆訂單編號")

        # 【新增】已取消的訂單不可再模擬任何狀態
        if cod.status == "cod_cancelled":
            raise ValueError("此訂單已取消，無法模擬")

        if not cod.store_id:
            raise ValueError("此訂單尚未選定取貨門市")
       
        # 【新增】舊資料沒有 trade_no 時補一個；成功後才存進 DB
        trade_no = cod.trade_no or self._new_trade_no()

        # 1. 先通知商店
        result = self._notify_store(
            merchant_trade_no=cod.merchant_trade_no,
            trade_amt=cod.trade_amt,
            status=target_status,
            trade_no=trade_no,          # 【新增】
            store_name=cod.store_name,
            store_address=cod.store_address,
            logistics_subtype=cod.logistics_subtype,
            simulate=True,          # 【新增】只有 simulate() 會帶標記
        )

        # 2. 商店成功後才寫 ecpay DB
        with transaction.atomic():
            cod = CODPaymentRequest.objects.select_for_update().get(
                merchant_trade_no=merchant_trade_no
            )
            cod.trade_no = trade_no     # 【新增】
            cod.status = target_status
            cod.shipped_at = (
                timezone.now() if action == "shipped" else None
            )
            cod.paid_at = (
                timezone.now() if action == "paid" else None
            )
            cod.save()

            # 共用 gateway.Order：paid / failed 照原本寫法，其餘退回 pending
            order = cod.order
            order.status = {
                "paid": "paid",
                "failed": "failed",
                "expired": "expired",   # 【新增】gateway.Order.status 已有 expired 選項
            }.get(action, "pending")
            order.save()

        return result