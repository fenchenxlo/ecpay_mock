from django.shortcuts import render, get_object_or_404, redirect

# Create your views here.
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import json, uuid, datetime ,random, string, httpx

from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest   # 匯入 Django 的回應物件，用來回傳字串或 JSON
from .models import Order,PaymentRequest, PaymentNotification          # 匯入 Order model，用來更新訂單狀態
from util.ChkMacVal import generate_check_mac_value
from django.conf import settings
from django.db import transaction, IntegrityError
from django.apps import apps
from datetime import timedelta
from .services import notify_shop_paid, notify_shop_failed

# Gateway呼叫Bank API
@csrf_exempt
def notify_bank(payment_data):
    """
    通知銀行建立虛擬帳號
    """

    payload = {
        "merchant_trade_no": payment_data["merchant_trade_no"],
        'bank_code': "013", # 國泰世華銀行代碼
        'v_account': f"013{random.randint(100000000000,999999999999)}", # 虛擬帳戶
        'expire_date': (datetime.datetime.now() + datetime.timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
        "trade_amt": str(payment_data["trade_amt"]),
#         "expire_date": payment_data["expire_date"].strftime("%Y-%m-%d %H:%M:%S"),
        "status": "atm_created",
#         "merchant_trade_no": payment_data["merchant_trade_no"],
#         "bank_code": payment_request.bank_code,
#         "v_account": payment_request.v_account,
#         "trade_amt": str(payment_request.trade_amt),
#         "expire_date": payment_request.expire_date.strftime("%Y-%m-%d %H:%M:%S"),
#         "status": payment_request.status,
    }
    print(payload["expire_date"])

    
    payload["CheckMacValue"] = (
        generate_check_mac_value(payload, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV)
    )

    try:

        response = httpx.post(

            f"{HF_SPACE_BANK_SITE_URL}/notify/create_account/",

            json=payload,

            timeout=10
        )
        
        print("status_code =", response.status_code)
        print("response.text =", response.text)
        
        if response.status_code != 200:
            return {
                "status": False
            }

        print("1")
        
        return response.json()

    except Exception as ex:

        print("銀行通知失敗")
        print(ex)
        
        return {
            "status": False,
            "message": str(ex)
        }
    
    return JsonResponse({
            "status":True
    })


## payment_notify
## 銀行mock call 綠界mock
@csrf_exempt
@transaction.atomic
def payment_notify(request):

    data = json.loads(request.body)
    print("data: ",data)
    recv_mac = data.pop(
        "CheckMacValue"
    )

    local_mac = (
        generate_check_mac_value(data,settings.ECPAY_HASH_KEY,settings.ECPAY_HASH_IV)
    )

    if recv_mac != local_mac:

        return JsonResponse({

            "status":"error",

            "message":"CheckMacValue Error"

        }, status=400)
    
    order = (
        Order.objects.get(
            order_number=
            data["merchant_trade_no"]
        )
    )
    payment = (
        PaymentRequest.objects.get(
            merchant_trade_no=
            data["merchant_trade_no"]
        )
    )
    
    payload = {
        "merchant_trade_no": data["merchant_trade_no"],
        "trade_amt": str(data["trade_amt"]),
        "bank_code": data["bank_code"],
        "v_account": data["v_account"],
        "expire_date": data["expire_date"],
        "status": data["status"],
#         "created_at": account.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    }
    
    # 付款成功
    if data["status"] == "paid":
        order.status = "paid"
        order.save()
        
        payment.status = "atm_paid"
        payment.save()

        PaymentNotification.objects.create(

            merchant_trade_no=payment.merchant_trade_no,

            trade_no=payment.trade_no,

            trade_amt=payment.trade_amt,

            payment_date=timezone.now(),

            choose_payment="ATM",

            payment_type="aio",

            rtn_code=1,

            rtn_msg="付款成功",

            simulate_paid=True
        )
        payload["transaction_id"] = payment.trade_no

        res = notify_shop_paid(payload)
        if res.status_code == 200:
            return JsonResponse({"status":"success"})
        else:
            return JsonResponse({"status":"failed"})
# 付款失敗
    else:
        order.status = "failed"
        order.save()
        
        payment.status = "atm_failed"
        payment.save()

        PaymentNotification.objects.create(

            merchant_trade_no=payment.merchant_trade_no,

            trade_no=payment.trade_no,

            trade_amt=payment.trade_amt,

            payment_date=timezone.now(),

            choose_payment="ATM",

            payment_type="aio",

            rtn_code=0,

            rtn_msg="付款失敗",

            simulate_paid=False
        )
        
        payload["transaction_id"] = payment.trade_no
        
        res = notify_shop_failed(payload)
        if res.status_code == 200:
            return JsonResponse({"status":"success"})
        else:
            return JsonResponse({"status":"failed"})


@csrf_exempt
def payment_info(request):
    return redirect('payment_info',{'HF_SPACE_E_COMMERCE_URL': settings.HF_SPACE_E_COMMERCE_URL})

# 建立 ATM 訂單 ,及顯示ATM資訊頁面, 並通知銀行端
@csrf_exempt
@transaction.atomic
def ecpay_gateway_checkout(request):
    """
    模擬綠界建立訂單 API (商城呼叫這個 view)
    - 接收商城送來的訂單資料
    - 在綠界 DB 建立 Order,PaymentRequest
    - 產生 ATM 虛擬帳號、繳費期限
    - 回傳 HTML form (模擬綠界行為)
    """

    if request.method != "POST":
        return HttpResponse("method error")

    try:
#         if request.content_type == "application/json":
#             payment_data = json.loads(request.body.decode("utf-8"))
            
        payment_data = request.POST.dict() if request.POST else request.body
            # 如果商城端用 JSON 傳送
        if isinstance(payment_data, (bytes, bytearray)):
            payment_data = json.loads(payment_data.decode("utf-8"))
#            payment_data  = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return HttpResponseBadRequest("JSON 格式錯誤")
#    payment_data = request.POST.dict()
    
    received_mac = payment_data.copy()

    received_mac = received_mac.pop("check_mac_value","")
    payment_data1 = payment_data.pop("check_mac_value","")
    expected_mac = generate_check_mac_value(
        payment_data,
        settings.ECPAY_HASH_KEY,
        settings.ECPAY_HASH_IV
    )
    
#     print("received_mac =", received_mac)
#     print("expected_mac =", expected_mac)
#     print("payment_data =", payment_data)

#     merchant_trade_date = timezone.localtime().strftime("%Y-%m-%d %H:%M:%S")
    merchant_trade_date = payment_data.get("merchant_trade_date")

    if received_mac != expected_mac:
        return HttpResponse(
            "CheckMacValue Error",
            status=400
        )
#     print("payment_data: " ,payment_data)
    merchant_trade_no = payment_data.get("merchant_trade_no") # 訂單編號
    print("merchant_trade_no: ",merchant_trade_no)
    
    payment_data["check_mac_value"] = received_mac
    payment_data["status"] = "atm_created"
    res_status = notify_bank(payment_data)
    print("res_status =", res_status)
    print(type(res_status))
        
    if res_status["status"] == False:
        error_url = f"{settings.HF_SPACE_E_COMMERCE_URL}/commerce_shop/payment_error/"
#        print("redirect to error_url =", error_url)   # 先加這行確認實際值
        return redirect(error_url)        
#             return redirect(f'{HF_SPACE_E_COMMERCE_UR}/commerce_shop/purchased_products/')
#             return JsonResponse({
#                 "tags":"error",
#                 "messages": ["銀行通知失敗: VirtualAccount取得或建立失敗"],
#             })
#             return HttpResponse(
#                 "銀行通知失敗: VirtualAccount取得或建立失敗",
#                 status=400
#             )
    
    with transaction.atomic():
        
        order_obj, create = Order.objects.get_or_create(
            order_number=merchant_trade_no,
            defaults={
                'user_id': payment_data["user_id"],
                'receiver_name': "王大明",
                'amount': payment_data["trade_amt"],
                'status': payment_data["status"],
            }
        )

        
        payment_request, created = PaymentRequest.objects.get_or_create(
            merchant_trade_no=merchant_trade_no,  # 查找條件
            defaults={
                'merchant_id': payment_data.get("merchant_id", "shop1234"),
                'merchant_trade_date': merchant_trade_date,
                'trade_amt': payment_data.get("trade_amt"),
                'trade_desc': payment_data.get("trade_desc", "商品交易"),
                'item_name': payment_data.get("item_name"),
                'choose_payment': payment_data.get("choose_payment", "ATM"),
                'payment_type': payment_data.get("payment_type", "aio"),
                'trade_no': payment_data.get("transaction_id"),
                'status': "atm_created",
                'return_url': payment_data.get("ReturnURL", f"{settings.HF_SPACE_E_COMMERCE_URL}/commerce_shop/ecpay_mock_notify/"),
                'payment_info_url': payment_data.get("PaymentInfoUrl", f"{settings.HF_SPACE_ECPAY_MOCK_URL}/gateway/payment_info/"),
                'order_result_url': payment_data.get("OrderResultURL", f"{settings.HF_SPACE_E_COMMERCE_URL}/commerce_shop/payment_ok/"),
                'check_mac_value': received_mac,
                'bank_code': "013", # 國泰世華銀行代碼
                'v_account': f"013{random.randint(100000000000,999999999999)}", # 虛擬帳戶
                'expire_date': (datetime.datetime.now() + datetime.timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        
    bank_code = payment_request.bank_code
    v_account = payment_request.v_account
    expire_date = payment_request.expire_date
    
    if bank_code == None and v_account == None:
        # 產生 ATM 虛擬帳號
        bank_code = payment_request.bank_code = bank_code = "013"  # 國泰世華
        v_account = payment_request.v_account = f"{bank_code}{random.randint(100000000000,999999999999)}"
        expire_date = payment_request.expire_date = (datetime.datetime.now() + datetime.timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")

#     print("bank_code:", bank_code)
#     print("v_account:", v_account)
#     print("expire_date:", expire_date)
    content_js = {
        'merchant_id': payment_data.get("merchant_id", "shop1234"),
        'merchant_trade_no': merchant_trade_no,
        'merchant_trade_date': merchant_trade_date,
        'user_id': payment_data["user_id"],
        'trade_amt': payment_data["trade_amt"],
        'trade_desc': payment_data["trade_desc"],
        'item_name': payment_data["item_name"],
        'choose_payment': payment_data["choose_payment"],
        'payment_type': payment_data["payment_type"],
        'trade_no': payment_data["transaction_id"],
        'return_url': payment_data["ReturnURL"],
        'payment_info_url': payment_data["PaymentInfoUrl"],
        'order_result_url': payment_data["OrderResultURL"],
        'bank_code': bank_code,
        'v_account': v_account,
        'expire_date': expire_date,
        'status': "atm_created",
    }
    content_js["check_mac_value"] = generate_check_mac_value(content_js,settings.ECPAY_HASH_KEY,settings.ECPAY_HASH_IV)
    
#     content_js = json.dumps(content_js, ensure_ascii=False)
    print("content_js: ",content_js)
#     content = {'content_js': content_js}
    content = {
        "content_js_dict": content_js,  # 原始 dict，給模板顯示用
        "content_js_json": json.dumps(content_js, ensure_ascii=False, default=str),  # JSON 字串，給 JS 用
        "HF_SPACE_E_COMMERCE_URL": settings.HF_SPACE_E_COMMERCE_URL
    }
    
    return render(request, "atm_info.html", content)


@csrf_exempt
@transaction.atomic
def simulate_bank_paid(request):

    if request.method != "POST":
        return HttpResponse("method error")

    try:            
        payment_payload = request.POST.dict() if request.POST else request.body
        print("1")
        # 如果商城端用 JSON 傳送
        if isinstance(payment_payload, (bytes, bytearray)):
            payment_payload = json.loads(payment_payload.decode("utf-8"))
            print("payment_payload: ",payment_payload)
    except json.JSONDecodeError:
        return HttpResponseBadRequest("JSON 格式錯誤")
    print("2")
    
    received_mac = payment_payload.copy()

    received_mac = received_mac.pop("check_mac_value","")
    payment_payload1 = payment_payload.pop("check_mac_value","")
    expected_mac = generate_check_mac_value(
        payment_payload,
        settings.ECPAY_HASH_KEY,
        settings.ECPAY_HASH_IV
    )

    print("received_mac =", received_mac)
    print("expected_mac =", expected_mac)
    print("payment_payload =", payment_payload)    
    
    if received_mac != expected_mac:
        return HttpResponse(
            "CheckMacValue Error",
            status=400
        )
    merchant_trade_no = payment_payload.get("merchant_trade_no") # 訂單編號
    payment_request = PaymentRequest.objects.get(
        merchant_trade_no=merchant_trade_no,  # 查找條件
    )
    # payment_request = get_object_or_404(
    #     PaymentRequest,
    #     merchant_trade_no=merchant_trade_no
    # )
    print("payment_request: ", payment_request)
    payment_request.status = "atm_paid"
    payment_request.save()
    
    order, created = Order.objects.get_or_create(
            order_number=merchant_trade_no,  # 查找條件:訂單編號
            defaults={
                'user_id': payment_payload["user_id"],
                'receiver_name': "王大明",
                'amount': payment_payload["trade_amt"],
                'status': "paid",
            }
        )
    print("3")
#     payment.order.status = status["paid"]
#     payment.order.amount = payment.trade_amt
#     payment.order.receiver_name = "xxx"
#     payment.order.save()
    
    if payment_request.status == "atm_paid":
#         return HttpResponse("已付款")
    
#     if PaymentNotification.objects.filter(
#         merchant_trade_no=payment.merchant_trade_no
#         ).exists():
#         return HttpResponse("已付款")    

        payment_notification = PaymentNotification.objects.create(

            merchant_trade_no=payment_request.merchant_trade_no,

            trade_no=payment_request.trade_no,

            trade_amt=payment_request.trade_amt,

#             payment_date=timezone.now(),datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            payment_date=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            
            choose_payment=payment_request.choose_payment,

            payment_type=payment_request.payment_type,

            rtn_code=1,

            rtn_msg="交易成功",

            simulate_paid=True,
        )
#     print("payment_notification: ",payment_notification)
    payment_payload = {
        'merchant_id': payment_payload.get("merchant_id", "shop1234"),
        'merchant_trade_no': merchant_trade_no,
        'merchant_trade_date': payment_payload["merchant_trade_date"],
        'user_id': payment_payload["user_id"],
        'trade_amt': payment_payload["trade_amt"],
        'trade_desc': payment_payload["trade_desc"],
        'item_name': payment_payload["item_name"],
        'choose_payment': payment_payload["choose_payment"],
        'payment_type': payment_payload["payment_type"],
        'trade_no': payment_payload["trade_no"],
        'return_url': payment_payload["return_url"],
        'payment_info_url': payment_payload["payment_info_url"],
        'order_result_url': payment_payload["order_result_url"],
        'bank_code': payment_payload["bank_code"],
        'v_account': payment_payload["v_account"],
        'expire_date': payment_payload["expire_date"],
    }

    order_pay_at = f"{str(payment_notification.payment_date)}"
    print("order_pay_at:", order_pay_at)
    payment_payload["order_pay_at"] = order_pay_at
    payment_payload["check_mac_value"] = generate_check_mac_value(payment_payload,settings.ECPAY_HASH_KEY,settings.ECPAY_HASH_IV)
    
#     payment_payload = json.dumps(payment_payload, ensure_ascii=False, default=str)  # JSON 字串，給 JS 用
    content = {"payment_payload": payment_payload}
    print("payment_payload: ", payment_payload)
    content = {
        "payment_payload_dict": payment_payload,  # 原始 dict，給模板顯示用
        "payment_payload_json": json.dumps(payment_payload, ensure_ascii=False, default=str)  # JSON 字串，給 JS 用
    }
#     return redirect('order_result', content)
#     return redirect('order_result')
#     return render(request, "redirect_html.html", payment_payload)
    return render(request, "redirect_html.html", content)

@csrf_exempt
def download_orderPayment_json(request):
    """讓店家下載指定訂單的完整金流交易資料 JSON 檔"""
    # 1. 從 URL 參數取得商店訂單編號 (例如: ?merchant_trade_no=202606110001)
#     merchant_trade_no = (request.POST.get("merchant_trade_no") or request.GET.get("merchant_trade_no"))
    body = json.loads(request.body)
    merchant_trade_no = body.get("merchant_trade_no")
    is_download = body.get("is_download")
    
    print("is_download: ", is_download)
    print("content_type =", request.content_type)
    print("POST =", request.POST)
    print("body =", request.body)
    if not merchant_trade_no:
        return JsonResponse({"error": "請提供 merchant_trade_no 參數"}, status=400)

    # 2. 獲取 Model (使用 apps.get_model 確保動態載入安全)
    Order = apps.get_model("gateway", "Order")
    PaymentRequest = apps.get_model("gateway", "PaymentRequest")
    PaymentNotification = apps.get_model("gateway", "PaymentNotification")

    # 3. 撈取資料 (找不到就回傳 404)
    # 註：Order 模型的欄位是 order_number，而綠界模型是 merchant_trade_no
    order = get_object_or_404(Order, order_number=merchant_trade_no)
    pay_req = PaymentRequest.objects.filter(
        merchant_trade_no=merchant_trade_no
    ).first()
    pay_note = PaymentNotification.objects.filter(
        merchant_trade_no=merchant_trade_no
    ).first()

#     # 4. 整理與分類資料（排除重複欄位，並轉換為基礎 Python 型態）
#     # --- [A] 商店點數/訂單基本資訊 (來自 Order) ---
#     order_data = {
#         "user_id": order.user_id,
#         "receiver_name": order.receiver_name,
#         "amount": int(order.amount),
#         "status": order.status,
#         "created_at": order.created_at.strftime("%Y-%m-%d %H:%M:%S"),
#     }
# 
#     # --- [B] 綠界付款請求資訊 (來自 PaymentRequest) ---
#     req_data = {}
#     atm_res_data = {}
#     if pay_req:
#         req_data = {
#             "merchant_id": pay_req.merchant_id,
#             "merchant_trade_date": pay_req.merchant_trade_date.strftime(
#                 "%Y-%m-%d %H:%M:%S"
#             ),
#             "trade_desc": pay_req.trade_desc,
#             "item_name": pay_req.item_name,
#             "payment_type": pay_req.payment_type,
#             "choose_payment": pay_req.choose_payment,
#             "return_url": pay_req.return_url,
#             "payment_info_url": pay_req.payment_info_url,
#             "order_result_url": pay_req.order_result_url,
#             "check_mac_value": pay_req.check_mac_value,
#         }
# 
#         # --- [C] 模擬綠界回傳給店家的 ATM 虛擬帳號資訊 (抽自 PaymentRequest) ---
#         atm_res_data = {
#             "bank_code": pay_req.bank_code,
#             "v_account": pay_req.v_account,
#             "expire_date": pay_req.expire_date.strftime("%Y-%m-%d %H:%M:%S"),
#             "trade_no": pay_req.trade_no,  # 綠界交易編號
#             "status": pay_req.status,
#         }
# 
#     # --- [D] 綠界付款成功通知資訊 (來自 PaymentNotification) ---
#     note_data = {}
#     if pay_note:
#         note_data = {
#             "trade_amt": int(pay_note.trade_amt),
#             "payment_date": pay_note.payment_date.strftime("%Y-%m-%d %H:%M:%S"),
#             "rtn_code": pay_note.rtn_code,
#             "rtn_msg": pay_note.rtn_msg,
#             "simulate_paid": pay_note.simulate_paid,
#         }

#     # 5. 組合成你要求的巢狀 JSON 結構
#     download_data = {
#         "merchant_trade_no": merchant_trade_no,  # 識別主鍵放最外層
#         "order_info": order_data,
#         "payment_request": req_data,
#         "atm_response": atm_res_data,
#         "payment_notification": note_data,
#     }

    download_data = {
        "merchant_trade_no": merchant_trade_no,

        "order_info": {
            "user_id": order.user_id,
            "receiver_name": order.receiver_name,
            "amount": int(order.amount),
            "status": order.status,
            "created_at": order.created_at.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        },

        "payment_request": {
            "merchant_id": pay_req.merchant_id,
            "merchant_trade_date": pay_req.merchant_trade_date.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "trade_desc": pay_req.trade_desc,
            "item_name": pay_req.item_name,
            "payment_type": pay_req.payment_type,
            "choose_payment": pay_req.choose_payment,
            "return_url": pay_req.return_url,
            "payment_info_url": pay_req.payment_info_url,
            "order_result_url": pay_req.order_result_url,
            "check_mac_value": pay_req.check_mac_value,
        },

        "atm_response": {
            "bank_code": pay_req.bank_code,
            "v_account": pay_req.v_account,
            "expire_date": pay_req.expire_date.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "trade_no": pay_req.trade_no,
            "status": pay_req.status,
        },

        "payment_notification": {
            "trade_amt": int(pay_note.trade_amt),
            "payment_date": pay_note.payment_date.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "rtn_code": pay_note.rtn_code,
            "rtn_msg": pay_note.rtn_msg,
            "simulate_paid": pay_note.simulate_paid,
        }
    }
    
    
    # 6. 強制瀏覽器將回應視為「檔案下載」
    response = JsonResponse(
        download_data,  json_dumps_params={"ensure_ascii": False, "indent": 4}
    )
    if is_download == "download":
        response["Content-Disposition"] = (
            f'attachment; filename="ecpay_data_{merchant_trade_no}.json"'
        )

    return response

def export_api_schema(request):
    """
    匯出 gateway app 的 API Schema
    重複欄位只保留一份
    """

    model_names = [
        "Order",
        "PaymentRequest",
        "PaymentNotification",
    ]

    schema = {}

    for model_name in model_names:

        model = apps.get_model("gateway", model_name)

        for field in model._meta.fields:

            if field.name == "id":
                continue

            # 已存在則跳過（避免重複）
            if field.name in schema:
                continue
            
            field_info = {
                "type": field.get_internal_type(),
                "required": not field.null,
            }

            if hasattr(field, "max_length") and field.max_length:
                field_info["max_length"] = field.max_length

            if field.help_text:
                field_info["description"] = str(field.help_text)

            schema[field.name] = field_info

    return JsonResponse(
        {
            "app": "gateway",
            "models": model_names,
            "fields": schema,
        },
        json_dumps_params={"ensure_ascii": False, "indent": 4},
    )


def order_result(request):
    
#     if request.method != "POST":
#         return HttpResponse("method error")

    try:            
        context = request.POST.dict() if request.POST else request.body
        print("context:" ,context)
        # 如果商城端用 JSON 傳送
        if isinstance(context, (bytes, bytearray)):
            context = json.loads(context.decode("utf-8"))
            print("context: ",context)
    except json.JSONDecodeError:
        return HttpResponseBadRequest("JSON 格式錯誤")
    print("2")
    
    received_mac = context.copy()

    received_mac = received_mac.pop("check_mac_value","")
    context1 = context.pop("check_mac_value","")
    expected_mac = generate_check_mac_value(
        context,
        settings.ECPAY_HASH_KEY,
        settings.ECPAY_HASH_IV
    )

    print("received_mac =", received_mac)
    print("expected_mac =", expected_mac)
    print("context =", context)    
    
    if received_mac != expected_mac:
        return HttpResponse(
            "CheckMacValue Error",
            status=400
        )
    context["check_mac_value"] = generate_check_mac_value(context,settings.ECPAY_HASH_KEY,settings.ECPAY_HASH_IV)
#     context = json.dumps(context, ensure_ascii=False)
    content = {'content_js': context}
    html = f"""
    <form id="f" action=f"{HF_SPACE_E_COMMERCE_URL}/commerce_shop/payment_ok/" method="post">
        <input type="hidden" name="content_js" value="{content['content_js']}">
    </form>
    <script>
        document.getElementById('f').submit();
    </script>
    """
    return HttpResponse(html)

@csrf_exempt
def ecpay_checkout(request):
    """
    模擬綠界建立訂單 API (商城呼叫這個 view)
    - 接收商城送來的訂單資料
    - 在綠界 DB 建立 PaymentRequest
    - 產生 ATM 虛擬帳號、繳費期限
    - 回傳 HTML form (模擬綠界行為)
    """
    if request.method == "POST":
        try:
            data = request.POST.dict() if request.POST else request.body
            # 如果商城端用 JSON 傳送
            if isinstance(data, (bytes, bytearray)):
                data = json.loads(data.decode("utf-8"))
#             data = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return HttpResponseBadRequest("JSON 格式錯誤")

        # 建立 PaymentRequest
        payment_request = PaymentRequest.objects.create(
            merchant_id = data.get("MerchantID", "shop1234"),
            merchant_trade_no = data.get("MerchantTradeNo"), # 訂單編號
            merchant_trade_date = timezone.localtime().strftime("%Y/%m/%d %H:%M:%S"),
            user_id = data.get("UserId"),
            trade_amt = data.get("TradeAmt"),
            trade_desc = data.get("TradeDesc","商品交易"),
            item_name = data.get("ItemName"),
            choose_payment = data.get("ChoosePayment", "ATM"), # 預設為ATM
            payment_type = data.get("PaymentType", "aio"),  # 預設 aio
            trade_no = data.get("TransactionID"),  # 模擬綠界交易編號
            status = data.get("Status"), # 訂單狀態
            order = Order.objects.get(order_number=data.get("MerchantTradeNo")),
            return_url = data.get("ReturnURL", f"{HF_SPACE_E_COMMERCE_URL}/commerce_shop/ecpay_mock_notify/"), # server-to-server callback, # 綠界回傳 URL
            payment_info_url = data.get("PaymentInfoUrl", f"{HF_SPACE_E_COMMERCE_URL}/commerce_shop/payment_info/"),  # 綠界通知商城已取虛擬帳號
            order_result_url = data.get("OrderResultURL", f"{HF_SPACE_E_COMMERCE_URL}/commerce_shop/payment-ok/"), # browser redirect ,瀏覽器跳轉 URL
            check_mac_value = data.get("CheckMacValue"),
        )
        
        # 產生 ATM 虛擬帳號
        bank_code = "013"  # 國泰世華
        v_account = f"{bank_code}{random.randint(100000000000,999999999999)}"
        expire_date = (datetime.datetime.now() + datetime.timedelta(days=3)).strftime("%Y/%m/%d %H:%M:%S")

        if not all([payment_request.merchant_trade_no, payment_request.trade_amt, payment_requestitem_name, payment_request.choose_payment, payment_request.payment_type, payment_request.trade_no, payment_request.return_url, payment_request.order_result_url]):
            return HttpResponseBadRequest("缺少必要欄位")
        
        # 更新 PaymentRequest (模擬綠界回傳)
        payment_request.bank_code = bank_code
        payment_request.v_account = v_account
        payment_request.expire_date = expire_date
        payment_request.save()
        
               
        html_form = f"""
            <html>
            <head>
                <meta charset="UTF-8">
                <title>ATM 虛擬帳號付款資訊</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 40px; }}
                    .info {{ border: 1px solid #ccc; padding: 20px; width: 400px; }}
                    .label {{ font-weight: bold; }}
                </style>
            </head>
            <body>
                <h1>ATM 虛擬帳號付款資訊</h1>
                <div class="info">
                    <p><span class="label">銀行代碼：</span>{bank_code} (國泰世華銀行)</p>
                    <p><span class="label">虛擬帳號：</span>{v_account}</p>
                    <p><span class="label">繳費期限：</span>{expire_date}</p>
                    <p>請於期限內至 ATM 或網銀完成轉帳。</p>
                </div>

                <!-- 保留原本的 html_form，但嵌在這裡 -->
                <form method="post" action="{payment_request.payment_info_url}">
                    <input type="hidden" name="MerchantID" value="{{ payment_request.merchant_id }}">
                    <input type="hidden" name="MerchantTradeNo" value="{payment_request.merchant_trade_no}">
                    <input type="hidden" name="MerchantTradeDate" value="{{ payment_request.merchant_trade_date }}">
                    <input type="hidden" name="TradeAmt" value="{{ payment_request.trade_amt }}">
                    <input type="hidden" name="TradeDesc" value="{{ payment_request.trade_desc }}">
                    <input type="hidden" name="ItemName" value="{{ payment_request.item_name }}">
                    <input type="hidden" name="ChoosePayment" value="{{ payment_request.choose_payment }}">
                    <input type="hidden" name="PaymentType" value="{{ payment_request.payment_type }}">
                    <input type="hidden" name="TradeNo" value="{payment_request.trade_no}">
                    <input type="hidden" name="Status" value="{{ payment_request.status }}">
                    <input type="hidden" name="BankCode" value="{bank_code}">
                    <input type="hidden" name="vAccount" value="{v_account}">
                    <input type="hidden" name="ExpireDate" value="{expire_date}">                                                                        
                    <!-- 綠界官方定義 -->
                    <input type="hidden" name="ReturnURL" value="{{ payment_request.return_url }}">
                    <input type="hidden" name="PaymentInfoUrl" value="{{ payment_request.payment_info_url }}">
                    <input type="hidden" name="OrderResultURL" value="{{ payment_request.order_result_url }}">
                    <input type="hidden" name="CheckMacValue" value="{{ payment_request.check_mac_value }}">
                    <button type="submit">返回商城</button>
                </form>
            </body>
            </html>
        """
        return HttpResponse(html_form)

    return HttpResponseBadRequest("請使用 POST 方法")


@csrf_exempt
def ecpay_mock_pay(request):
    if request.method == "POST":
        
        merchant_id = request.POST.get("MerchantID", "shop1234")
        merchant_trade_no = request.POST.get("MerchantTradeNo") # 訂單編號
        merchant_trade_date = request.POST.get("MerchantTradeDate", datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
        trade_amt = request.POST.get("TradeAmt")  # 總金額
        trade_desc = request.POST.get("TradeDesc")
        item_name = request.POST.get("ItemName", "無名稱") # 商品名稱
        payment_type = request.POST.get("PaymentType", "ATM")  # 預設 ATM
        trade_no = request.POST.get("TradeNo")
#         status = request.POST.get("Status") # 訂單狀態
        return_url = request.POST.get("ReturnURL", f"{HF_SPACE_E_COMMERCE_UR}/ecpay_mock_notify/")
        order_result_url = request.POST.get("OrderResultURL", f"{HF_SPACE_E_COMMERCE_UR}/payment-ok/")
        
        # 模擬產生 ATM 虛擬帳號與繳費期限
        bank_code = "013"  # 國泰世華銀行代碼
        atm_account = f"{bank_code}{random.randint(100000000000, 999999999999)}"
#         atm_account = f"{random.randint(100,999)}-{random.randint(100000,999999)}"
        expire_date = (datetime.datetime.now() + datetime.timedelta(days=3)).strftime("%Y/%m/%d %H:%M:%S")

        # 模擬綠界回傳 HTML form
        context = {
            "MerchantID": merchant_id,
            "MerchantTradeNo": merchant_trade_no,
            "MerchantTradeDate": merchant_trade_date,
            "TradeAmt": trade_amt,
            "TradeDesc": trade_desc,
            "ItemName": item_name,  
            "PaymentType": payment_type,
            "TradeNo": trade_no,
            "BankCode" : bank_code,
            "ATMAccount": atm_account,
            "ExpireDate": expire_date,
            "ReturnURL": return_url,
            "OrderResultURL": order_result_url,
        }

        return render(request, "atm_payment.html", {"context":context})

@csrf_exempt
def ecpay_notify(request):                           # 定義一個 view，模擬綠界的 notify
    if request.method == "POST":                     # 只允許 POST 請求
        merchant_trade_no = request.POST.get("MerchantTradeNo")  # 從 POST 取出商店訂單編號
        trade_no = request.POST.get("TradeNo")                   # 綠界交易編號
        trade_amt = request.POST.get("TradeAmt")                 # 交易金額
        payment_date = request.POST.get("PaymentDate")           # 付款完成時間
        payment_type = request.POST.get("PaymentType")           # 付款方式 (ATM / Credit)
        rtn_code = request.POST.get("RtnCode")                   # 回傳代碼 (1=成功)
        rtn_msg = request.POST.get("RtnMsg")                     # 回傳訊息 (交易成功/失敗)

        try:
            order = Order.objects.get(order_number=merchant_trade_no)  # 查詢對應的訂單
        except Order.DoesNotExist:
            # 如果找不到訂單，回傳錯誤 JSON
            return JsonResponse({"status": "error", "message": "Order Not Found"}, status=404)

        # 更新訂單狀態
        if rtn_code == "1":                                # 如果交易成功
            order.status = "paid"                          # 更新訂單狀態為已付款
            order.payment_date = payment_date              # 記錄付款時間
            order.payment_type = payment_type              # 記錄付款方式
            order.trade_no = trade_no                      # 記錄綠界交易編號
            order.save()                                   # 存檔更新到資料庫
        else:
            order.status = "failed"                        # 如果失敗，更新狀態為失敗
            order.save()

        # 準備完整的交易內容回傳給商城端
        notify_data = {
            "MerchantTradeNo": merchant_trade_no,          # 商店訂單編號
            "TradeNo": trade_no,                           # 綠界交易編號
            "TradeAmt": trade_amt,                         # 交易金額
            "PaymentDate": payment_date,                   # 付款完成時間
            "PaymentType": payment_type,                   # 付款方式
            "RtnCode": rtn_code,                           # 回傳代碼
            "RtnMsg": rtn_msg,                             # 回傳訊息
            "OrderStatus": order.status,                   # 商城訂單狀態
        }

        return JsonResponse(notify_data)                   # 回傳 JSON 給商城端，包含完整交易明細

    # 如果不是 POST 請求，回傳錯誤 JSON
    return JsonResponse({"status": "error", "message": "Invalid Method"}, status=400)

# @csrf_exempt
# def ecpay_notify(request):
#     if request.method == "POST":
#         merchant_trade_no = request.POST.get("MerchantTradeNo")
#         trade_no = request.POST.get("TradeNo")
#         trade_amt = request.POST.get("TradeAmt")
#         payment_date = request.POST.get("PaymentDate")
#         payment_type = request.POST.get("PaymentType")
#         rtn_code = request.POST.get("RtnCode")
#         rtn_msg = request.POST.get("RtnMsg")
# 
#         # 更新訂單狀態
#         try:
#             order = Order.objects.get(order_number=merchant_trade_no)
#             if rtn_code == "1":  # 交易成功
#                 order.status = "paid"
#                 order.save()
#         except Order.DoesNotExist:
#             return HttpResponse("0|Order Not Found")
# 
#         # 模擬綠界回傳格式
#         return HttpResponse("1|OK")
# 
#     return HttpResponse("0|Invalid Method")
