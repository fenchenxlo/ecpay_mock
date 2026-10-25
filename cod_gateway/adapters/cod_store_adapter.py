# ============================================================
# 【新增】ecpay_mock → E_commerce COD Adapter
# 負責：重新簽章 CheckMacValue + httpx
# ============================================================

import logging
from typing import Any, Dict

import httpx
from django.conf import settings

from util.ChkMacVal import generate_check_mac_value

from ..interface.cod_store_gateway import CODStoreGateway

logger = logging.getLogger(__name__)


class CODStoreAdapter(CODStoreGateway):

    def __init__(self):
        base_url = (
            getattr(settings, "HF_SPACE_E_COMMERCE_URL", "") or ""
        ).rstrip("/")
        self.callback_url = (
            f"{base_url}/commerce_shop/cod_payment_notify/"
        )
        self.timeout = 10.0

    def notify_cod_status(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:

        if not self.callback_url.startswith("http"):
            raise RuntimeError("未設定 HF_SPACE_E_COMMERCE_URL")

        # 簽章前先移除舊 MAC，再重新計算
        body = dict(payload)
        body.pop("CheckMacValue", None)
        body["CheckMacValue"] = generate_check_mac_value(
            body,
            settings.ECPAY_HASH_KEY,
            settings.ECPAY_HASH_IV,
        )

        logger.info(
            "ecpay_mock → E_commerce COD callback: %s",
            self.callback_url,
        )

        try:
            response = httpx.post(
                self.callback_url,
                json=body,
                timeout=self.timeout,
            )
        except httpx.RequestError as exc:
            logger.exception("COD callback HTTPX 失敗")
            return {
                "success": False,
                "status_code": 0,
                "message": f"商店連線失敗：{exc}",
                "response_data": {},
            }

        try:
            data = response.json()
            if not isinstance(data, dict):
                data = {"raw_response": data}
        except ValueError:
            data = {"raw_response": response.text}

        # HTTP 2xx，且商店沒有明確回 success=False
        success = (
            200 <= response.status_code < 300
            and data.get("success") is not False
        )

        return {
            "success": success,
            "status_code": response.status_code,
            "message": str(
                data.get("message", "")
                or ("商店處理成功" if success else "商店處理失敗")
            ),
            "response_data": data,
        }