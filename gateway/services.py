import httpx
from util.ChkMacVal import generate_check_mac_value
from django.conf import settings
import logging          # 【新增】

logger = logging.getLogger(__name__)   # 【新增】

## notify_shop_paid
def notify_shop_paid(payload):

#     payload = {
#         "merchant_trade_no": payment.merchant_trade_no,
#         "trade_amt": str(payment.trade_amt),
#         "status": "paid",
# #         "created_at": payment.created_at,
#     }

    payload["CheckMacValue"] = (
        generate_check_mac_value(payload, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV)
    )
    
    response = httpx.post(

        f"{settings.HF_SPACE_E_COMMERCE_URL}/commerce_shop/payment_callback/",

        json=payload,

        timeout=10
    )
    logger.info("SHOP URL:", settings.HF_SPACE_E_COMMERCE_URL}/commerce_shop/payment_callback/)
    logger.info("SHOP STATUS:", response.status_code)
    logger.info("SHOP RESPONSE:", response.text)
    return response

## notify_shop_failed
def notify_shop_failed(payload):

#     payload = {
#         "merchant_trade_no":payment.merchant_trade_no,
#         "trade_amt":str(payment.trade_amt),
#         "status":"failed",
# #         "created_at": payment.created_at,
#     }

    payload["CheckMacValue"] = (
        generate_check_mac_value(payload, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV)
    )

    response = httpx.post(

        f"{settings.HF_SPACE_E_COMMERCE_URL}/commerce_shop/payment_callback/",

        json=payload,

        timeout=10
    )

    logger.info("SHOP URL:", settings.HF_SPACE_E_COMMERCE_URL}/commerce_shop/payment_callback/)
    logger.info("SHOP STATUS:", response.status_code)
    logger.info("SHOP RESPONSE:", response.text)
    return response

