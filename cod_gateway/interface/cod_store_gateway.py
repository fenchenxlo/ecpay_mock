# ============================================================
# 【新增】ecpay_mock → E_commerce COD Gateway Interface
# ============================================================

from abc import ABC, abstractmethod
from typing import Any, Dict


class CODStoreGateway(ABC):
    """通知商店 COD 狀態。實作只能在 Adapter（httpx 只存在 Adapter）。"""

    @abstractmethod
    def notify_cod_status(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        ...