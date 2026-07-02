from django.shortcuts import render

# Create your views here.
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponseBadRequest

import json, uuid, datetime ,random

from django.http import HttpResponseBadRequest
from django.http import HttpResponse, JsonResponse   # 匯入 Django 的回應物件，用來回傳字串或 JSON
from .models import Order           # 匯入 Order model，用來更新訂單狀態
from util.ChkMacVal import generate_check_mac_value

@csrf_exempt
def ecpay_checkout(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return HttpResponseBadRequest("JSON 格式錯誤")

        merchant_id = data.get("MerchantID", "shop1234")
        merchant_trade_no = data.get("MerchantTradeNo") # 訂單編號
        merchant_trade_date = data.get("MerchantTradeDate", datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
        user_id = data.get("UserId")
        trade_amt = data.get("TradeAmt")  # 總金額
        trade_desc = data.get("TradeDesc")
        item_name = data.get("ItemName", "無名稱") # 商品名稱
        choose_payment = data.get("ChoosePayment", "ATM"),
        payment_type = data.get("PaymentType", "aio")  # 預設 ATM
        trade_no = data.get("TransactionID")
#         status = data.get("Status") # 訂單狀態
        return_url = data.get("ReturnURL", "http://127.0.0.1:8000/gateway/ecpay_mock_notify/")
        order_result_url = data.get("OrderResultURL", "http://127.0.0.1:8000/gateway/payment-ok/")
        
        
        if not all([merchant_trade_no, trade_amt, item_name, payment_type, trade_no, return_url, order_result_url]):
            return HttpResponseBadRequest("缺少必要欄位")
       
       # 查詢訂單，串接商品名稱
#         try:
#             order = Order.objects.get(order_number=merchant_trade_no)
#             item_names = "#".join([item.product.name for item in order.items.all()])
#         except Order.DoesNotExist:
#             item_names = "未知商品"

        # 模擬綠界回傳 HTML form
        context = {
            "MerchantID": merchant_id,
            "MerchantTradeNo": merchant_trade_no,
            "MerchantTradeDate": merchant_trade_date,
            "UserId": user_id,
            "TradeAmt": trade_amt,
            "TradeDesc": trade_desc,
            "ItemName": item_name,
            "ChoosePayment": choose_payment,
            "PaymentType": payment_type,
            "TradeNo": trade_no, # 交易編號
            "ReturnURL": return_url,
            "OrderResultURL": order_result_url,
        }
        # 產生 CheckMacValue
        context["CheckMacValue"] = generate_check_mac_value(context)
        return render(request, "payment_form.html", {"context":context})

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