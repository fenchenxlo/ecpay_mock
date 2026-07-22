from django.shortcuts import render, redirect
# Create your views here.
import json
import traceback

from django.conf import settings
from django.db import transaction, IntegrityError
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse

from django.views.decorators.csrf import csrf_exempt

from gateway.models import Order  # 只 import 共用 model,不修改 gateway app 任何檔案
from util.ChkMacVal import generate_check_mac_value
from .models import CODPaymentRequest


# ─────────────────────────────────────────────
# 模擬門市清單(demo 用固定座標,不用真的串接綠界電子地圖 API)
# ─────────────────────────────────────────────
MOCK_STORES = [
    {"store_id": "991182", "name": "7-ELEVEN 桃園中正門市", "chain": "UNIMART",
     "address": "桃園市桃園區中正路100號", "lat": 24.9936, "lng": 121.3010},
    {"store_id": "991183", "name": "7-ELEVEN 桃園站前門市", "chain": "UNIMART",
     "address": "桃園市桃園區站前路50號", "lat": 24.9880, "lng": 121.3125},
    {"store_id": "006598", "name": "全家 桃園藝文店", "chain": "FAMI",
     "address": "桃園市桃園區藝文路20號", "lat": 24.9930, "lng": 121.3210},
    {"store_id": "2001", "name": "萊爾富 桃園復興店", "chain": "HILIFE",
     "address": "桃園市桃園區復興路88號", "lat": 24.9850, "lng": 121.3050},
    {"store_id": "OK1001", "name": "OK超商 桃園中山店", "chain": "OKMART",
     "address": "桃園市桃園區中山路15號", "lat": 24.9905, "lng": 121.3155},
]


def _log_and_build_error_response(view_name, exception, status=500):
    """
    共用錯誤處理小工具:
    - 在 Server 端印出完整錯誤類型、訊息、traceback,
      方便到 HF Space 的 Logs 分頁直接看到完整錯誤堆疊除錯
    - 回傳統一格式的 JSON 錯誤訊息給前端,包含：
        error_type  → Python 例外類別名稱(例如 KeyError, IntegrityError)
        message     → 例外的詳細訊息
        view        → 是在哪個 view 發生的,方便定位問題
    """
    error_type = type(exception).__name__
    error_message = str(exception)
    print(f"❌ [{view_name}] {error_type}: {error_message}")
    print(traceback.format_exc())  # 印出完整 traceback,包含行號、呼叫鏈
    return JsonResponse(
        {
            "status": "error",
            "view": view_name,
            "error_type": error_type,
            "message": error_message,
        },
        status=status,
    )


@csrf_exempt
@transaction.atomic
def cod_checkout(request):
    """
    模擬綠界建立「超商取貨付款」訂單(商城呼叫這個 view)
    與 gateway.ecpay_gateway_checkout 對稱,但不建立 ATM 帳號,
    而是建立 CODPaymentRequest,並導向「選擇取貨門市」頁面。

    流程:
    1. 檢查 HTTP method
    2. 解析商城傳來的資料(表單或 JSON 都支援)
    3. 驗證 CheckMacValue,防止資料被竄改
    4. 建立/取得 Order,再建立/取得 CODPaymentRequest(FK 指向該 Order)
    5. 把訂單編號存進 session,導向選店頁面
    """
    if request.method != "POST":
        return HttpResponse("method error", status=405)

    # ── Step 1: 解析請求資料 ──────────────────────────────
    try:
        payment_data = request.POST.dict() if request.POST else request.body
        if isinstance(payment_data, (bytes, bytearray)):
            payment_data = json.loads(payment_data.decode("utf-8"))
    except json.JSONDecodeError as e:
        return _log_and_build_error_response("cod_checkout.parse_request", e, status=400)
    except Exception as e:
        # 保底:任何解析階段沒預期到的錯誤都攔下來,避免整個 view 500 沒有任何線索
        return _log_and_build_error_response("cod_checkout.parse_request_unexpected", e, status=400)

    # ── Step 2: 驗證 CheckMacValue ────────────────────────
    try:
        received_mac = payment_data.pop("check_mac_value", "")
        expected_mac = generate_check_mac_value(
            payment_data, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV
        )
    except Exception as e:
        return _log_and_build_error_response("cod_checkout.generate_mac", e, status=400)

    if received_mac != expected_mac:
        print(f"⚠️ [cod_checkout] CheckMacValue 不符: received={received_mac}, expected={expected_mac}")
        return HttpResponse("CheckMacValue Error", status=400)

    # ── Step 3: 取出必要欄位(用 KeyError 攔截缺欄位的狀況)────
    try:
        merchant_trade_no = payment_data["merchant_trade_no"]
        merchant_trade_date = payment_data["merchant_trade_date"]
        user_id = payment_data["user_id"]
        trade_amt = payment_data["trade_amt"]
    except KeyError as e:
        # KeyError 訊息只會顯示缺的那個 key 名稱,例如 'merchant_trade_no'
        return _log_and_build_error_response(
            "cod_checkout.missing_required_field", e, status=400
        )

    # ── Step 4: 寫入資料庫(Order + CODPaymentRequest)──────
    try:
        with transaction.atomic():
            order_obj, _ = Order.objects.get_or_create(
                order_number=merchant_trade_no,
                defaults={
                    "user_id": user_id,
                    "receiver_name": payment_data.get("receiver_name", "王大明"),
                    "amount": trade_amt,
                    # COD 出貨前不預先收款,沿用現有 Order.status 的 "pending",
                    # 不新增 choices,避免動到共用 model
                    "status": "pending",
                },
            )

            cod_payment, created = CODPaymentRequest.objects.get_or_create(
                merchant_trade_no=merchant_trade_no,
                defaults={
                    "order": order_obj,
                    "merchant_trade_date": merchant_trade_date,
                    "trade_amt": trade_amt,
                    "item_name": payment_data.get("item_name", ""),
                    "receiver_name": payment_data.get("receiver_name", "王大明"),
                    "receiver_cell_phone": payment_data.get("receiver_cell_phone", ""),
                    "status": "cod_created",
                    "check_mac_value": received_mac,
                    "return_url": payment_data.get("ReturnURL", ""),
                    "order_result_url": payment_data.get("OrderResultURL", ""),
                },
            )
    except IntegrityError as e:
        # 常見情境：merchant_trade_no 已存在但關聯的 order 對不上、
        # 或必填欄位為 None 違反 NOT NULL 限制
        return _log_and_build_error_response("cod_checkout.db_integrity_error", e, status=409)
    except Exception as e:
        return _log_and_build_error_response("cod_checkout.db_write_unexpected", e, status=500)

    # ── Step 5: 存 session,導向選店頁 ──────────────────────
    try:
        request.session["cod_merchant_trade_no"] = merchant_trade_no
    except Exception as e:
        return _log_and_build_error_response("cod_checkout.session_write", e, status=500)

    return redirect("select_store")


def select_store(request):
    """
    模擬綠界電子地圖:顯示門市清單 + 小地圖,讓使用者選擇取貨門市。
    容易出錯的地方是 session 遺失(例如使用者重新整理、cookie 被擋),
    所以這裡明確檢查並回傳可讀的錯誤訊息,而不是讓 template render 時噴例外。
    """
    try:
        merchant_trade_no = request.session.get("cod_merchant_trade_no")
        if not merchant_trade_no:
            raise ValueError("找不到對應的訂單編號(session 已遺失),請重新從商城結帳")

        context = {
            "stores_json": json.dumps(MOCK_STORES, ensure_ascii=False),
            "merchant_trade_no": merchant_trade_no,
        }
        return render(request, "select_store.html", context)

    except ValueError as e:
        return _log_and_build_error_response("select_store.session_missing", e, status=400)
    except Exception as e:
        return _log_and_build_error_response("select_store.unexpected", e, status=500)


@csrf_exempt
def confirm_store(request):
    """
    使用者確認選擇的門市後,寫回 CODPaymentRequest,顯示取貨付款資訊頁。
    容易出錯的地方：
      - session 遺失
      - 前端送來的 store_id 不在 MOCK_STORES 清單裡(被竄改或過期)
      - CODPaymentRequest 對應不到資料(訂單編號打錯或已被刪除)
    都各自攔截,回傳清楚的錯誤訊息。
    """
    if request.method != "POST":
        return HttpResponse("method error", status=405)

    try:
        merchant_trade_no = request.session.get("cod_merchant_trade_no")
        if not merchant_trade_no:
            raise ValueError("session 已遺失,找不到對應訂單,請重新從商城結帳")

        store_id = request.POST.get("store_id")
        store = next((s for s in MOCK_STORES if s["store_id"] == store_id), None)
        if not store:
            raise ValueError(f"門市代號 '{store_id}' 不存在,請重新選擇")

    except ValueError as e:
        return _log_and_build_error_response("confirm_store.validate_input", e, status=400)
    except Exception as e:
        return _log_and_build_error_response("confirm_store.validate_input_unexpected", e, status=500)

    try:
        cod_payment = CODPaymentRequest.objects.get(merchant_trade_no=merchant_trade_no)
    except CODPaymentRequest.DoesNotExist as e:
        return _log_and_build_error_response("confirm_store.cod_payment_not_found", e, status=404)
    except Exception as e:
        return _log_and_build_error_response("confirm_store.db_read_unexpected", e, status=500)

    try:
        cod_payment.logistics_subtype = store["chain"]
        cod_payment.store_id = store["store_id"]
        cod_payment.store_name = store["name"]
        cod_payment.store_address = store["address"]
        cod_payment.store_lat = store["lat"]
        cod_payment.store_lng = store["lng"]
        cod_payment.save()
    except Exception as e:
        return _log_and_build_error_response("confirm_store.db_write", e, status=500)

    # session 用完即丟,避免下一筆訂單誤用到舊的 merchant_trade_no
    try:
        del request.session["cod_merchant_trade_no"]
    except KeyError:
        pass  # 已經不存在就不用處理,不影響主流程

    context = {
        "cod": cod_payment,
        "HF_SPACE_E_COMMERCE_URL": settings.HF_SPACE_E_COMMERCE_URL,
    }
    return render(request, "cod_info.html", context)