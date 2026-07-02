from django.shortcuts import render

# Create your views here.
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponseBadRequest
from django.utils import timezone
import json, uuid, datetime ,random

from django.http import HttpResponseBadRequest
from django.http import HttpResponse, JsonResponse   # 匯入 Django 的回應物件，用來回傳字串或 JSON
from .models import Order,PaymentRequest           # 匯入 Order model，用來更新訂單狀態
from util.ChkMacVal import generate_check_mac_value
from django.conf import settings
from django.db import transaction, IntegrityError


@csrf_exempt
def payment_info(request):
    return redirect('payment_info')
 
@csrf_exempt
@transaction.atomic
def ecpay_gateway_checkout(request):
    """
    模擬綠界建立訂單 API (商城呼叫這個 view)
    - 接收商城送來的訂單資料
    - 在綠界 DB 建立 PaymentRequest
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
    received_mac = payment_data.pop("CheckMacValue","")

    expected_mac = generate_check_mac_value(
        payment_data,
        settings.ECPAY_HASH_KEY,
        settings.ECPAY_HASH_IV
    )
    
    print("received_mac =", received_mac)
    print("expected_mac =", expected_mac)
    print("payment_data =", payment_data)

    # 商城訂單編號(綠界端唯一鍵)
    merchant_trade_no = payment_data.get("MerchantTradeNo")
    merchant_trade_date = timezone.localtime().strftime("%Y-%m-%d %H:%M:%S")

    # ==========================================
    # 先檢查這筆訂單是否已存在
    # ==========================================
    print(
        "Before:",
        list(
            PaymentRequest.objects.values(
                "id",
                "merchant_trade_no"
            )
        )
    )
    try:
        # 用 merchant_trade_no 查詢
        # 因為 model 已經設定 unique=True
        payment_request = PaymentRequest.objects.get(
            merchant_trade_no=merchant_trade_no
        )

        # 表示資料已存在
        created = False

    except PaymentRequest.DoesNotExist:

        # ==========================================
        # 資料不存在 -> 建立新的 PaymentRequest
        # ==========================================

        payment_request = PaymentRequest.objects.create(

            # 商店代號
            merchant_id=payment_data.get(
                "MerchantID",
                "shop1234"
            ),

            # 商城訂單編號
            merchant_trade_no=merchant_trade_no,

            # 訂單建立時間
            merchant_trade_date=merchant_trade_date,

            # 訂單金額
            trade_amt=payment_data.get("TradeAmt"),

            # 交易描述
            trade_desc=payment_data.get(
                "TradeDesc",
                "商品交易"
            ),

            # 商品名稱
            item_name=payment_data.get("ItemName"),

            # ATM
            choose_payment=payment_data.get(
                "ChoosePayment",
                "ATM"
            ),

            # aio
            payment_type=payment_data.get(
                "PaymentType",
                "aio"
            ),

            # 模擬綠界交易編號
            trade_no=payment_data.get(
                "TransactionID"
            ),

            # ATM 已建立
            status="atm_created",

            # 回傳網址
            return_url=payment_data.get(
                "ReturnURL"
            ),

            # ATM資訊通知網址
            payment_info_url=payment_data.get(
                "PaymentInfoUrl"
            ),

            # 完成付款後跳轉網址
            order_result_url=payment_data.get(
                "OrderResultURL"
            ),

            # CheckMacValue
            check_mac_value=expected_mac,

            # =====================================
            # ATM欄位先給預設值
            # 後面再更新
            # =====================================
            bank_code="",
            v_account="",
            expire_date=timezone.now() + datetime.timedelta(days=3),

            # 如果你的 FK 必填
            # 請取消註解
             order=Order.objects.get(order_number=merchant_trade_no),
        )

        created = True


    # ==========================================
    # 建立 ATM 虛擬帳號
    # ==========================================

    bank_code = "013"

    v_account = (
        f"{bank_code}"
        f"{random.randint(100000000000,999999999999)}"
    )

    expire_date = (
        timezone.now()
        + datetime.timedelta(days=3)
    )

    # ==========================================
    # 更新 ATM 資訊
    # ==========================================

    payment_request.bank_code = bank_code
    payment_request.v_account = v_account
    payment_request.expire_date = expire_date
    payment_request.status = "atm_created"

    # 寫回資料庫
    payment_request.save()

    print(
        "After:",
        list(
            PaymentRequest.objects.values(
                "id",
                "merchant_trade_no"
            )
        )
    )
    
    context = {
        "merchant_id": payment_data.get("MerchantID", "shop1234"),
        "merchant_trade_no": merchant_trade_no,
#         "merchant_trade_date": datetime.datetime.strptime(
#             merchant_trade_date,
#             "%Y/%m/%d %H:%M:%S"
#         ),
        "merchant_trade_date": merchant_trade_date,
        "user_id": payment_data["UserId"],
        "trade_amt": payment_data["TradeAmt"],
        "trade_desc": payment_data["TradeDesc"],
        "item_name": payment_data["ItemName"],
        "choose_payment": payment_data["ChoosePayment"],
        "payment_type": payment_data["PaymentType"],
        "trade_no": payment_data["TransactionID"],
        "return_url": payment_data["ReturnURL"],
        "payment_info_url": payment_data["PaymentInfoUrl"],
        "order_result_url": payment_data["OrderResultURL"],
        "check_mac_value": payment_data.get("CheckMacValue"),
        "bank_code": bank_code,
        "v_account": v_account,
        "expire_date": expire_date,
        "payment_data": payment_data,
    }

    return render(request, "ecpay_atm_info.html", context)


@csrf_exempt
@transaction.atomic
def ecpay_gateway_checkout_old(request):
    """
    模擬綠界建立訂單 API (商城呼叫這個 view)
    - 接收商城送來的訂單資料
    - 在綠界 DB 建立 PaymentRequest
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
    received_mac = payment_data.pop("CheckMacValue","")

    expected_mac = generate_check_mac_value(
        payment_data,
        settings.ECPAY_HASH_KEY,
        settings.ECPAY_HASH_IV
    )
    
#     print("received_mac =", received_mac)
#     print("expected_mac =", expected_mac)
#     print("payment_data =", payment_data)

    merchant_trade_date = timezone.localtime().strftime("%Y-%m-%d %H:%M:%S")

    if received_mac != expected_mac:
        return HttpResponse(
            "CheckMacValue Error",
            status=400
        )
    merchant_trade_no = payment_data.get("MerchantTradeNo") # 訂單編號
    try:
        # 建立 PaymentRequest
        payment_request, created = PaymentRequest.objects.get_or_create(
            merchant_id = payment_data.get("MerchantID", "shop1234"),
            merchant_trade_no=merchant_trade_no,
            merchant_trade_date = merchant_trade_date,
    #         user_id = payment_data.get("UserId"),
            trade_amt = payment_data.get("TradeAmt"),
            trade_desc = payment_data.get("TradeDesc","商品交易"),
            item_name = payment_data.get("ItemName"),
            choose_payment = payment_data.get("ChoosePayment", "ATM"), # 預設為ATM
            payment_type = payment_data.get("PaymentType", "aio"),  # 預設 aio
            trade_no = payment_data.get("TransactionID"),  # 模擬綠界交易編號
            status = "atm_created", # 訂單狀態
    #         order = Order.objects.get(order_number=payment_data.get("MerchantTradeNo")),
            return_url = payment_data.get("ReturnURL", "http://127.0.0.1:8000/commerce_shop/ecpay_mock_notify/"), # server-to-server callback, # 綠界回傳 URL
            payment_info_url = payment_data.get("PaymentInfoUrl", "http://127.0.0.1:8001/gateway/payment_info/"),  # 綠界通知商城已取虛擬帳號
            order_result_url = payment_data.get("OrderResultURL", "http://127.0.0.1:8000/commerce_shop/payment-ok/"), # browser redirect ,瀏覽器跳轉 URL
            check_mac_value = expected_mac,
        )
    except IntegrityError:
        payment_request = PaymentRequest.objects.get(merchant_trade_no=merchant_trade_no)
        created = False
#    merchant_trade_date=datetime.datetime.strptime(payment_data["MerchantTradeDate"],"%Y/%m/%d %H:%M:%S"),
    

    # 產生 ATM 虛擬帳號
    bank_code = "013"  # 國泰世華
    v_account = f"{bank_code}{random.randint(100000000000,999999999999)}"
    expire_date = (datetime.datetime.now() + datetime.timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")

#    expire_date = (timezone.now() + timedelta(days=3))
    
    payment_request.bank_code = bank_code
    payment_request.v_account = v_account
    payment_request.expire_date = expire_date
#     payment_request.status = payment_request.status["atm_created"]
    payment_request.save()

    context = {
        "merchant_id": payment_data.get("MerchantID", "shop1234"),
        "merchant_trade_no": merchant_trade_no,
#         "merchant_trade_date": datetime.datetime.strptime(
#             merchant_trade_date,
#             "%Y/%m/%d %H:%M:%S"
#         ),
        "merchant_trade_date": merchant_trade_date,
        "user_id": payment_data["UserId"],
        "trade_amt": payment_data["TradeAmt"],
        "trade_desc": payment_data["TradeDesc"],
        "item_name": payment_data["ItemName"],
        "choose_payment": payment_data["ChoosePayment"],
        "payment_type": payment_data["PaymentType"],
        "trade_no": payment_data["TransactionID"],
        "return_url": payment_data["ReturnURL"],
        "payment_info_url": payment_data["PaymentInfoUrl"],
        "order_result_url": payment_data["OrderResultURL"],
        "check_mac_value": payment_data.get("CheckMacValue"),
        "bank_code": bank_code,
        "v_account": v_account,
        "expire_date": expire_date,
    }

    return render(request, "ecpay_atm_info.html", context)


@csrf_exempt
@transaction.atomic
def simulate_bank_paid(request, merchant_trade_no):

    payment = get_object_or_404(
        PaymentRequest,
        merchant_trade_no=merchant_trade_no
    )

    payment.status = "atm_paid"
    payment.save()
    
    payment.order.status = "paid"
    payment.order.amount = payment.trade_amt
    payment.order.receiver_name = "xxx"
    payment.order.save()

    PaymentNotification.objects.create(

        merchant_trade_no=payment.merchant_trade_no,

        trade_no=payment.trade_no,

        trade_amt=payment.trade_amt,

        payment_date=timezone.now(),
        
        choose_payment="ATM",

        payment_type="aio",

        rtn_code=1,

        rtn_msg="交易成功",

        simulate_paid=True,
    )

    return redirect(payment.order_result_url)

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
            return_url = data.get("ReturnURL", "http://127.0.0.1:8000/commerce_shop/ecpay_mock_notify/"), # server-to-server callback, # 綠界回傳 URL
            payment_info_url = data.get("PaymentInfoUrl", "http://127.0.0.1:8000/commerce_shop/payment_info/"),  # 綠界通知商城已取虛擬帳號
            order_result_url = data.get("OrderResultURL", "http://127.0.0.1:8000/commerce_shop/payment-ok/"), # browser redirect ,瀏覽器跳轉 URL
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
        return_url = request.POST.get("ReturnURL", "http://127.0.0.1:8000/ecpay_mock_notify/")
        order_result_url = request.POST.get("OrderResultURL", "http://127.0.0.1:8000/payment-ok/")
        
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