from ninja import NinjaAPI

from commerce_shop.schemas.checkout import CheckoutSchema

from commerce_shop.services.order_service import (
    OrderService,
)

from commerce_shop.services.payment_service import (
    PaymentService,
)

from commerce_shop.gateways.ecpay_mock_adapter import (
    ECPayMockAdapter,
)


api = NinjaAPI()


# ============================================================
# 建立 Gateway
# ============================================================

ecpay_gateway = ECPayMockAdapter(
    merchant_id="2000132"
)


# ============================================================
# 建立 PaymentService
# ============================================================

payment_service = PaymentService(
    ecpay_gateway=ecpay_gateway,

    merchant_id="2000132",
)


# ============================================================
# 建立 OrderService
# ============================================================

order_service = OrderService(
    payment_service=payment_service
)


# ============================================================
# Checkout API
# ============================================================

@api.post("/checkout")
def checkout(
    request,
    data: CheckoutSchema,
):

    # --------------------------------------------------------
    # Django Ninja request.user
    # --------------------------------------------------------

    user_id = request.user.id

    # --------------------------------------------------------
    # 呼叫 OrderService
    # --------------------------------------------------------

    result = order_service.checkout(

        user_id=user_id,

        receiver_name=data.receiver_name,

        amount=data.amount,

        item_name=data.item_name,

        choose_payment=data.choose_payment,
    )

    order = result["order"]

    # --------------------------------------------------------
    # ATM
    # --------------------------------------------------------

    if result["payment_request"]:

        payment = result["payment"]

        return {
            "success": True,

            "message": "訂單建立成功，ATM付款資訊已產生",

            "order": {
                "order_number": (
                    order.order_number
                ),

                "amount": str(
                    order.amount
                ),

                "status": order.status,
            },

            "payment": {
                "merchant_trade_no": (
                    payment["merchant_trade_no"]
                ),

                "trade_no": (
                    payment["trade_no"]
                ),

                "bank_code": (
                    payment["bank_code"]
                ),

                "v_account": (
                    payment["v_account"]
                ),

                "expire_date": (
                    payment["expire_date"]
                    .isoformat()
                ),

                "status": payment["status"],
            },
        }

    # --------------------------------------------------------
    # COD
    # --------------------------------------------------------

    return {
        "success": True,

        "message": "訂單建立成功",

        "order": {
            "order_number": (
                order.order_number
            ),

            "amount": str(
                order.amount
            ),

            "status": order.status,
        },

        "payment": {
            "choose_payment": "COD",

            "status": "pending",
        },
    }