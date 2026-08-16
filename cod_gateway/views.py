from django.shortcuts import render, redirect
# Create your views here.
import json,httpx,uuid
import traceback
import datetime	 # 【新增】用於解析 merchant_trade_date 字串

from django.conf import settings
from django.db import transaction, IntegrityError, connection
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.contrib.auth.decorators import user_passes_test
from django.views.decorators.csrf import csrf_exempt

from gateway.models import Order  # 只 import 共用 model,不修改 gateway app 任何檔案
from util.ChkMacVal import generate_check_mac_value
from .models import CODPaymentRequest
from gateway.services import notify_shop_paid, notify_shop_failed  # 【重點】直接沿用既有的 notify_shop_paid/failed，不用重寫
from django.utils import timezone  # 【新增】
import logging			# 【新增】

logger = logging.getLogger(__name__)   # 【新增】

# ─────────────────────────────────────────────
# 模擬門市清單(demo 用固定座標,不用真的串接綠界電子地圖 API)
# ─────────────────────────────────────────────
MOCK_STORES = [
    # ─────────────────────────────────────────────
    # 桃園市 10 間
    # ─────────────────────────────────────────────
    {
        "store_id": "TY001",
        "name": "7-ELEVEN 桃園中正門市",
        "chain": "UNIMART",
        "address": "桃園市桃園區中正路100號",
        "lat": 24.9936,
        "lng": 121.3010,
    },
    {
        "store_id": "TY002",
        "name": "7-ELEVEN 桃園站前門市",
        "chain": "UNIMART",
        "address": "桃園市桃園區站前路50號",
        "lat": 24.9880,
        "lng": 121.3125,
    },
    {
        "store_id": "TY003",
        "name": "全家 桃園藝文店",
        "chain": "FAMI",
        "address": "桃園市桃園區藝文路20號",
        "lat": 24.9930,
        "lng": 121.3210,
    },
    {
        "store_id": "TY004",
        "name": "全家 中壢火車站店",
        "chain": "FAMI",
        "address": "桃園市中壢區中和路200號",
        "lat": 24.9538,
        "lng": 121.2258,
    },
    {
        "store_id": "TY005",
        "name": "萊爾富 桃園復興店",
        "chain": "HILIFE",
        "address": "桃園市桃園區復興路88號",
        "lat": 24.9850,
        "lng": 121.3050,
    },
    {
        "store_id": "TY006",
        "name": "OK超商 桃園中山店",
        "chain": "OKMART",
        "address": "桃園市桃園區中山路15號",
        "lat": 24.9905,
        "lng": 121.3155,
    },
    {
        "store_id": "TY007",
        "name": "7-ELEVEN 楊梅新城店",
        "chain": "UNIMART",
        "address": "桃園市楊梅區新城路30號",
        "lat": 24.9100,
        "lng": 121.1450,
    },
    {
        "store_id": "TY008",
        "name": "全家 龜山長庚店",
        "chain": "FAMI",
        "address": "桃園市龜山區復興一路150號",
        "lat": 25.0600,
        "lng": 121.3650,
    },
    {
        "store_id": "TY009",
        "name": "萊爾富 八德廣福店",
        "chain": "HILIFE",
        "address": "桃園市八德區廣福路100號",
        "lat": 24.9580,
        "lng": 121.2980,
    },
    {
        "store_id": "TY010",
        "name": "OK超商 蘆竹南崁店",
        "chain": "OKMART",
        "address": "桃園市蘆竹區南崁路200號",
        "lat": 25.0460,
        "lng": 121.2950,
    },
] 
# ─────────────────────────────────────────────
 # 新竹市 10 間 
# ───────────────────────────────────────────── 

MOCK_STORES.extend([
    {
        "store_id": "HC001",
        "name": "7-ELEVEN 新竹東門店",
        "chain": "UNIMART",
        "address": "新竹市東區東門街50號",
        "lat": 24.8047,
        "lng": 120.9685,
    },
    {
        "store_id": "HC002",
        "name": "7-ELEVEN 新竹科園店",
        "chain": "UNIMART",
        "address": "新竹市東區光復路二段200號",
        "lat": 24.7989,
        "lng": 120.9937,
    },
    {
        "store_id": "HC003",
        "name": "全家 新竹火車站店",
        "chain": "FAMI",
        "address": "新竹市東區中正路1號",
        "lat": 24.8010,
        "lng": 120.9710,
    },
    {
        "store_id": "HC004",
        "name": "全家 清大店",
        "chain": "FAMI",
        "address": "新竹市東區光復路二段101號",
        "lat": 24.7950,
        "lng": 120.9960,
    },
    {
        "store_id": "HC005",
        "name": "萊爾富 新竹北大店",
        "chain": "HILIFE",
        "address": "新竹市北區北大路120號",
        "lat": 24.8100,
        "lng": 120.9650,
    },
    {
        "store_id": "HC006",
        "name": "OK超商 新竹南大店",
        "chain": "OKMART",
        "address": "新竹市東區南大路80號",
        "lat": 24.7955,
        "lng": 120.9680,
    },
    {
        "store_id": "HC007",
        "name": "7-ELEVEN 香山店",
        "chain": "UNIMART",
        "address": "新竹市香山區中華路五段50號",
        "lat": 24.7600,
        "lng": 120.9200,
    },
    {
        "store_id": "HC008",
        "name": "全家 新竹巨城店",
        "chain": "FAMI",
        "address": "新竹市東區中央路229號",
        "lat": 24.8090,
        "lng": 120.9740,
    },
    {
        "store_id": "HC009",
        "name": "萊爾富 新竹竹科店",
        "chain": "HILIFE",
        "address": "新竹市東區研新路88號",
        "lat": 24.7800,
        "lng": 121.0100,
    },
    {
        "store_id": "HC010",
        "name": "OK超商 新竹光復店",
        "chain": "OKMART",
        "address": "新竹市東區光復路一段300號",
        "lat": 24.7830,
        "lng": 120.9900,
    },
])


# ───────────────────────────────────────────── 
# 台北市 10 間 
# ─────────────────────────────────────────────

MOCK_STORES.extend([
    {
        "store_id": "TP001",
        "name": "7-ELEVEN 台北信義店",
        "chain": "UNIMART",
        "address": "台北市信義區信義路五段20號",
        "lat": 25.0330,
        "lng": 121.5654,
    },
    {
        "store_id": "TP002",
        "name": "7-ELEVEN 台北車站店",
        "chain": "UNIMART",
        "address": "台北市中正區忠孝西路一段50號",
        "lat": 25.0478,
        "lng": 121.5170,
    },
    {
        "store_id": "TP003",
        "name": "全家 台北西門店",
        "chain": "FAMI",
        "address": "台北市萬華區成都路50號",
        "lat": 25.0420,
        "lng": 121.5060,
    },
    {
        "store_id": "TP004",
        "name": "全家 大安森林店",
        "chain": "FAMI",
        "address": "台北市大安區信義路三段100號",
        "lat": 25.0335,
        "lng": 121.5350,
    },
    {
        "store_id": "TP005",
        "name": "萊爾富 中山店",
        "chain": "HILIFE",
        "address": "台北市中山區南京東路二段80號",
        "lat": 25.0522,
        "lng": 121.5327,
    },
    {
        "store_id": "TP006",
        "name": "OK超商 松山店",
        "chain": "OKMART",
        "address": "台北市松山區八德路四段200號",
        "lat": 25.0490,
        "lng": 121.5600,
    },
    {
        "store_id": "TP007",
        "name": "7-ELEVEN 士林店",
        "chain": "UNIMART",
        "address": "台北市士林區中正路300號",
        "lat": 25.0950,
        "lng": 121.5250,
    },
    {
        "store_id": "TP008",
        "name": "全家 南港店",
        "chain": "FAMI",
        "address": "台北市南港區忠孝東路六段100號",
        "lat": 25.0480,
        "lng": 121.5900,
    },
    {
        "store_id": "TP009",
        "name": "萊爾富 內湖店",
        "chain": "HILIFE",
        "address": "台北市內湖區成功路四段100號",
        "lat": 25.0830,
        "lng": 121.5950,
    },
    {
        "store_id": "TP010",
        "name": "OK超商 北投店",
        "chain": "OKMART",
        "address": "台北市北投區北投路二段50號",
        "lat": 25.1320,
        "lng": 121.4980,
    },
])

# ─────────────────────────────────────────────
# 新北市 10 間
# ─────────────────────────────────────────────

MOCK_STORES.extend([
    {
        "store_id": "NT001",
        "name": "7-ELEVEN 板橋文化店",
        "chain": "UNIMART",
        "address": "新北市板橋區文化路一段120號",
        "lat": 25.0118,
        "lng": 121.4618,
    },
    {
        "store_id": "NT002",
        "name": "7-ELEVEN 新店中正店",
        "chain": "UNIMART",
        "address": "新北市新店區中正路200號",
        "lat": 24.9700,
        "lng": 121.5410,
    },
    {
        "store_id": "NT003",
        "name": "全家 三重重新店",
        "chain": "FAMI",
        "address": "新北市三重區重新路二段80號",
        "lat": 25.0610,
        "lng": 121.4880,
    },
    {
        "store_id": "NT004",
        "name": "全家 永和中山店",
        "chain": "FAMI",
        "address": "新北市永和區中山路一段100號",
        "lat": 25.0100,
        "lng": 121.5120,
    },
    {
        "store_id": "NT005",
        "name": "萊爾富 淡水中正店",
        "chain": "HILIFE",
        "address": "新北市淡水區中正路50號",
        "lat": 25.1670,
        "lng": 121.4450,
    },
    {
        "store_id": "NT006",
        "name": "OK超商 新莊中正店",
        "chain": "OKMART",
        "address": "新北市新莊區中正路300號",
        "lat": 25.0369,
        "lng": 121.4500,
    },
    {
        "store_id": "NT007",
        "name": "7-ELEVEN 汐止車站店",
        "chain": "UNIMART",
        "address": "新北市汐止區新台五路一段100號",
        "lat": 25.0680,
        "lng": 121.6620,
    },
    {
        "store_id": "NT008",
        "name": "全家 土城中央店",
        "chain": "FAMI",
        "address": "新北市土城區中央路二段150號",
        "lat": 24.9730,
        "lng": 121.4430,
    },
    {
        "store_id": "NT009",
        "name": "萊爾富 蘆洲長安店",
        "chain": "HILIFE",
        "address": "新北市蘆洲區長安街100號",
        "lat": 25.0820,
        "lng": 121.4590,
    },
    {
        "store_id": "NT010",
        "name": "OK超商 林口文化店",
        "chain": "OKMART",
        "address": "新北市林口區文化三路一段200號",
        "lat": 25.0700,
        "lng": 121.3620,
    },
])
# ─────────────────────────────────────────────
# 基隆市 10 間
# ─────────────────────────────────────────────

MOCK_STORES.extend([
    {
        "store_id": "KL001",
        "name": "7-ELEVEN 基隆仁愛店",
        "chain": "UNIMART",
        "address": "基隆市仁愛區愛三路30號",
        "lat": 25.1283,
        "lng": 121.7419,
    },
    {
        "store_id": "KL002",
        "name": "7-ELEVEN 基隆火車站店",
        "chain": "UNIMART",
        "address": "基隆市仁愛區港西街5號",
        "lat": 25.1330,
        "lng": 121.7390,
    },
    {
        "store_id": "KL003",
        "name": "全家 基隆廟口店",
        "chain": "FAMI",
        "address": "基隆市仁愛區仁三路50號",
        "lat": 25.1280,
        "lng": 121.7440,
    },
    {
        "store_id": "KL004",
        "name": "全家 基隆信一路店",
        "chain": "FAMI",
        "address": "基隆市中正區信一路100號",
        "lat": 25.1370,
        "lng": 121.7480,
    },
    {
        "store_id": "KL005",
        "name": "萊爾富 基隆安樂店",
        "chain": "HILIFE",
        "address": "基隆市安樂區安樂路二段80號",
        "lat": 25.1300,
        "lng": 121.7200,
    },
    {
        "store_id": "KL006",
        "name": "OK超商 基隆中正店",
        "chain": "OKMART",
        "address": "基隆市中正區中正路200號",
        "lat": 25.1470,
        "lng": 121.7700,
    },
    {
        "store_id": "KL007",
        "name": "7-ELEVEN 七堵店",
        "chain": "UNIMART",
        "address": "基隆市七堵區明德一路100號",
        "lat": 25.0950,
        "lng": 121.7140,
    },
    {
        "store_id": "KL008",
        "name": "全家 暖暖店",
        "chain": "FAMI",
        "address": "基隆市暖暖區源遠路50號",
        "lat": 25.0990,
        "lng": 121.7360,
    },
    {
        "store_id": "KL009",
        "name": "萊爾富 八斗子店",
        "chain": "HILIFE",
        "address": "基隆市中正區北寧路200號",
        "lat": 25.1450,
        "lng": 121.7950,
    },
    {
        "store_id": "KL010",
        "name": "OK超商 基隆東明店",
        "chain": "OKMART",
        "address": "基隆市信義區東明路80號",
        "lat": 25.1290,
        "lng": 121.7580,
    },
])

class ShopNotifyError(Exception):
	"""
	【新增】商城(E_commerce)通知失敗時拋出的自訂例外。
	獨立出一個例外類別,是為了讓「通知商城失敗」這件事,
	在 transaction.atomic() 區塊裡也能觸發資料庫 rollback——
	如果商城收不到這筆確認(或商城自己處理失敗回傳非 200),
	ecpay_mock 這邊就不該留下「已經選定門市」的紀錄,
	否則兩邊資料會不一致(ecpay_mock 覺得已確認,商城卻不知道)。
	"""
	pass

def _log_and_build_error_response(view_name, exception, status=500):
	"""
	共用錯誤處理小工具:
	- 在 Server 端印出完整錯誤類型、訊息、traceback,
	  方便到 HF Space 的 Logs 分頁直接看到完整錯誤堆疊除錯
	- 回傳統一格式的 JSON 錯誤訊息給前端,包含：
		error_type	→ Python 例外類別名稱(例如 KeyError, IntegrityError)
		message		→ 例外的詳細訊息
		view		→ 是在哪個 view 發生的,方便定位問題
	"""
	error_type = type(exception).__name__
	error_message = str(exception)
	logger.exception(f"❌ [{view_name}] {error_type}: {error_message}")
	logger.exception(traceback.format_exc())  # 印出完整 traceback,包含行號、呼叫鏈
#	 print(f"❌ [{view_name}] {error_type}: {error_message}")
#	 print(traceback.format_exc())	# 印出完整 traceback,包含行號、呼叫鏈
	return JsonResponse(
		{
			"status": "error",
			"view": view_name,
			"error_type": error_type,
			"message": error_message,
		},
		status=status,
	)


def is_admin(user):
    """判斷是否為已登入的管理員(superuser) —— 若 cod_gateway/views.py 目前沒有這個 function，複製這段過來即可"""
    return user.is_authenticated and user.is_superuser

@user_passes_test(is_admin, login_url='/admin/login/')
def db_query_tool(request):
    """
    資料庫查詢工具:
    流程 —— 使用者先選擇 table,選定後列出該 table 所有欄位,
    再選擇「兩個」欄位(column1、column2),查詢這兩個欄位
    「同一列(同一筆資料)」對應的值,例如 order_number 對應 status。

    重點:兩個欄位必須放在同一個 SELECT 裡一起查,才能保證
    回傳的每一筆 (col1值, col2值) 確實來自同一列資料,
    而不是像分開查兩次那樣,兩份清單各自篩選、順序對不上。
    """
    tables = []          # 所有可查詢的 table 名稱
    columns = []          # 目前選定 table 的欄位名稱清單
    rows = []              # 查詢結果,每筆是 (col1值, col2值) 的 tuple
    error = None           # 查詢過程中若有錯誤,存放錯誤訊息

    table_choice = request.GET.get('table', '')      # 使用者選擇的 table 名稱
    column1_choice = request.GET.get('column1', '')  # 使用者選擇的第一個欄位
    column2_choice = request.GET.get('column2', '')  # 使用者選擇的第二個欄位

    with connection.cursor() as cursor:
        # 1. 取得資料庫中所有「業務用」table
        #    排除 sqlite 系統表、django 內建表、auth 相關表,避免查到不該看的系統資料
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' "
            "AND name NOT LIKE 'django_%' "
            "AND name NOT LIKE 'auth_%';"
        )
        tables = [r[0] for r in cursor.fetchall()]

        # 2. 若使用者有選擇 table,且該 table 確實存在於允許清單中
        #    (白名單檢查,防止使用者從網址列竄改 table 參數)
        if table_choice and table_choice in tables:
            # 2-1. 取得該 table 的所有欄位名稱(給使用者選擇用)
            cursor.execute(f"PRAGMA table_info({table_choice});")
            columns = [r[1] for r in cursor.fetchall()]

            # 3. 兩個欄位都要有選,且都存在於這個 table 的欄位清單中(白名單檢查),
            #    且不能選成同一個欄位(對應兩個一樣的東西沒有意義)
            if (column1_choice and column2_choice
                    and column1_choice in columns
                    and column2_choice in columns
                    and column1_choice != column2_choice):
                try:
                    # 3-1. 關鍵修改:col1、col2 放在同一個 SELECT 裡一起撈,
                    #      確保同一列回傳的兩個值是「同一筆資料」的對應值。
                    #      table_choice / column1_choice / column2_choice
                    #      都已經過白名單檢查,用 f-string 組 SQL 是安全的。
                    #      加上 ORDER BY rowid,確保每次查詢順序固定一致。
                    query = (
                        f"SELECT {column1_choice}, {column2_choice} "
                        f"FROM {table_choice} "
                        f"WHERE {column1_choice} IS NOT NULL "
                        f"AND {column2_choice} IS NOT NULL "
                        f"ORDER BY rowid;"
                    )
                    cursor.execute(query)
                    # 直接存成 tuple list:[(col1值, col2值), (col1值, col2值), ...]
                    rows = [(r[0], r[1]) for r in cursor.fetchall()]
                except Exception as e:
                    # 查詢過程中若發生錯誤(例如欄位型別問題),記錄錯誤訊息
                    error = str(e)

    context = {
        'tables': tables,
        'columns': columns,
        'rows': rows,
        'error': error,
        'table_choice': table_choice,
        'column1_choice': column1_choice,
        'column2_choice': column2_choice,
    }
    return render(request, 'admin_tools/db_query.html', context)

@csrf_exempt
@user_passes_test(is_admin, login_url='/admin/login/')
def query_and_simulate_cod(request):
    """
    合併頁面（COD 版）:左側是 SQL 查詢工具（邏輯與 Bank_site 版本完全相同，原樣搬過來），
    右側改為「超商取貨付款」模擬工具。

    這是 COD 流程的起點頁面，跟 Bank_site 的 query_and_simulate 互不影響、
    也跟 db_query_tool 互不影響。
    """
    tables = []
    columns = []
    rows = []
    error = None
    table_choice = request.GET.get('table', '')
    column_choice = request.GET.get('column', '')

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' "
            "AND name NOT LIKE 'django_%' "
            "AND name NOT LIKE 'auth_%';"
        )
        tables = [r[0] for r in cursor.fetchall()]

        if table_choice and table_choice in tables:
            cursor.execute(f"PRAGMA table_info({table_choice});")
            columns = [r[1] for r in cursor.fetchall()]

            if column_choice and column_choice in columns:
                try:
                    query = (
                        f"SELECT {column_choice} FROM {table_choice} "
                        f"WHERE {column_choice} IS NOT NULL;"
                    )
                    cursor.execute(query)
                    rows = [{column_choice: r[0]} for r in cursor.fetchall()]
                except Exception as e:
                    error = str(e)

    context = {
        'tables': tables,
        'columns': columns,
        'rows': rows,
        'error': error,
        'table_choice': table_choice,
        'column_choice': column_choice,
    }
    return render(request, 'admin_tools/query_simulate_cod.html', context)

@csrf_exempt
@user_passes_test(is_admin, login_url='/admin/login/')
def simulate_cod_paid(request, merchant_trade_no):
    """
    【新增】COD 版模擬付款起點。
    重點差異:因為起點就在 ecpay_mock 自己身上，不像 ATM 流程還要先經過
    Bank_site 打一次 payment_notify，這裡直接把「更新自己狀態」+
    「通知 E_commerce」兩件事做完，等同合併了 Bank_site.simulate_paid
    和 Ecpay_mock.payment_notify 這兩層的工作。
    """

    try:
        cod_request = CODPaymentRequest.objects.get(merchant_trade_no=merchant_trade_no)
    except CODPaymentRequest.DoesNotExist:
        return JsonResponse({"status": "failed", "message": "找不到該筆訂單編號"}, status=44)

    # 更新 ecpay_mock 自己這邊（cod_gateway app）的狀態
    cod_request.status = "cod_paid"
    cod_request.paid_at = timezone.now()
    cod_request.save()

    # 同步更新共用的 gateway.Order（跟 payment_notify 裡 order.status = "paid" 對應）
    order = cod_request.order
    order.status = "paid"
    order.save()

    payload = {
        "merchant_trade_no": cod_request.merchant_trade_no,
        "trade_amt": int(cod_request.trade_amt),
        "status": "paid",
        # 【新增】transaction_id：COD 沒有像 PaymentRequest.trade_no 這種欄位，
        # 用 merchant_trade_no 頂替（本身 unique，可以安全當 Payment.transaction_id 用）
#        "transaction_id": cod_request.merchant_trade_no,
        "transaction_id": str(uuid.uuid4()),
        # 【新增】讓 E_commerce 那邊分得出這筆是 COD、不是 ATM
        "payment_method": "COD",
        "cvs_store_name": str(cod_request.store_name or ""),
        "cvs_store_address": str(cod_request.store_address or ""),
    }

    # payload["CheckMacValue"] = (
        # generate_check_mac_value(payload, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV)
    # )

    try:
        # 沿用既有的 notify_shop_paid，內部本來就是通用的 httpx.post，不用改
        res = notify_shop_paid(payload)
        if res.status_code == 200:
            return JsonResponse({"status": "success", "message": "模擬付款成功，已同步通知商店！"})
        else:
            return JsonResponse({"status": "failed", "error": res.text}, status=400)
    except Exception as ex:
        return JsonResponse({"status": "failed", "message": str(ex)}, status=500)

@csrf_exempt
@user_passes_test(is_admin, login_url='/admin/login/')
def simulate_cod_failed(request, merchant_trade_no):
    """【新增】COD 版模擬「未取貨/退貨」，邏輯與 simulate_cod_paid 對稱"""
    try:
        cod_request = CODPaymentRequest.objects.get(merchant_trade_no=merchant_trade_no)
    except CODPaymentRequest.DoesNotExist:
        return JsonResponse({"status": "failed", "message": "找不到該筆訂單編號"}, status=44)

    # 【注意】CODPaymentRequest.status 目前的 choices 只有
    # cod_created / cod_shipped / cod_paid，沒有失敗狀態，
    # 下面這行如果要存進 DB，choices 需要你另外加一個 ("cod_failed", "取貨失敗/退貨") 才會通過表單驗證
    cod_request.status = "cod_failed"
    cod_request.save()

    order = cod_request.order
    order.status = "failed"
    order.save()

    payload = {
        "merchant_trade_no": cod_request.merchant_trade_no,
        "trade_amt": int(cod_request.trade_amt),
        "status": "failed",
#        "transaction_id": cod_request.merchant_trade_no,
        "transaction_id": str(uuid.uuid4()),
        "payment_method": "COD",
        "cvs_store_name": str(cod_request.store_name or ""),
        "cvs_store_address": str(cod_request.store_address or ""),
    }
    # payload["CheckMacValue"] = (
        # generate_check_mac_value(payload, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV)
    # )

    try:
        res = notify_shop_failed(payload)
        if res.status_code == 200:
            return JsonResponse({"status": "success", "message": "模擬付款成功，已同步通知商店！"})
        else:
            return JsonResponse({"status": "failed", "error": res.text}, status=400)
    except Exception as ex:
        return JsonResponse({"status": "failed", "message": str(ex)}, status=500)

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
		merchant_trade_date_raw = payment_data["merchant_trade_date"]  # 【修改】先當原始字串接住
		user_id = payment_data["user_id"]
		trade_amt = payment_data["trade_amt"]

		# 【新增】E_commerce 那邊是用 strftime("%Y-%m-%d %H:%M:%S") 傳字串過來的,
		# 這裡的 model 欄位是 DateTimeField,直接存字串在 sqlite 上「看起來正常」,
		# 但不保證所有資料庫後端都相容,所以先轉成真正的 datetime 物件
		try:
			merchant_trade_date = datetime.datetime.strptime(
				merchant_trade_date_raw, "%Y-%m-%d %H:%M:%S"
			)
		except (ValueError, TypeError) as e:
			return _log_and_build_error_response(
				"cod_checkout.invalid_trade_date_format", e, status=400
			)
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

			# 【修改】get_or_create → update_or_create
			# 原本用 get_or_create,如果這筆 merchant_trade_no 已經存在(例如使用者重新整理、
			# 重新走一次結帳流程),defaults 裡的新資料(receiver_name 等)完全不會被拿來更新,
			# 只會撈出舊紀錄直接回傳,導致收件人姓名/地址等欄位卡在第一次建立時的舊值(甚至空值)。
			# 改成 update_or_create 後,不管這筆紀錄存不存在,defaults 都會被寫入/覆蓋,
			# 確保每次使用者重新確認收件資訊時,COD 這邊的紀錄都會同步更新成最新資料。
			# 注意:defaults 裡沒有包含 store_id/store_name 等門市欄位,所以已經選定的門市
			# 不會被這次更新清空(update_or_create 只動 defaults 裡明確列出的欄位)。
			cod_payment, created = CODPaymentRequest.objects.update_or_create(
				merchant_trade_no=merchant_trade_no,
				defaults={
					"order": order_obj,
					"merchant_trade_date": merchant_trade_date,	 # 【修改】改用轉型後的 datetime 物件
					"trade_amt": trade_amt,
					"item_name": payment_data.get("item_name", ""),
					"receiver_name": payment_data.get("receiver_name", "王大明"),
					"receiver_cell_phone": payment_data.get("receiver_cell_phone", ""),
					"receiver_address": payment_data.get("receiver_address", ""),
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
	使用者在確認頁按下「確認送出」後,真正把門市資訊寫進 CODPaymentRequest,
	並用 httpx 通知商城(E_commerce)這筆訂單已確認超商取貨付款。

	【修改】原本「通知商城失敗只印錯誤、不影響使用者看到確認頁」的邏輯是錯的——
	這樣會讓 ecpay_mock 和 E_commerce 兩邊資料不一致。改成:
	門市寫入 + 通知商城 一起包進同一個 transaction.atomic(),
	只要通知商城失敗(連線錯誤,或商城回應非 200),就拋出 ShopNotifyError,
	讓這次的門市寫入也跟著 rollback,並回應清楚的錯誤頁面,
	附上返回商店訂單頁面的按鈕,讓使用者可以重新操作。
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

	# 防止同一筆訂單被重複確認門市(連點兩次、瀏覽器返回上一頁重送)——這段不變動
	if cod_payment.store_id:
		logger.info(f"[confirm_store] 訂單 {merchant_trade_no} 已確認過門市,直接顯示既有結果")
		try:
			del request.session["cod_merchant_trade_no"]
		except KeyError:
			pass
		context = {"cod": cod_payment, "HF_SPACE_E_COMMERCE_URL": settings.HF_SPACE_E_COMMERCE_URL}
		return render(request, "cod_info.html", context)

	# ── 【修改】門市寫入 + 通知商城,包進同一個 transaction.atomic() ──────
	# 只要通知商城失敗,整個區塊(包含 cod_payment.save())都會自動 rollback,
	# 不會留下「ecpay_mock 已確認,商城不知道」的不一致狀態。
	try:
		with transaction.atomic():
			cod_payment.logistics_subtype = store["chain"]
			cod_payment.store_id = store["store_id"]
			cod_payment.store_name = store["name"]
			cod_payment.store_address = store["address"]
			cod_payment.store_lat = store["lat"]
			cod_payment.store_lng = store["lng"]
			cod_payment.save()

			notify_payload = {
				"merchant_trade_no": cod_payment.merchant_trade_no,
				"store_name": cod_payment.store_name,
				"store_address": cod_payment.store_address,
				"logistics_subtype": cod_payment.logistics_subtype,
			}
			notify_payload["check_mac_value"] = generate_check_mac_value(
				notify_payload, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV
			)
			notify_url = f"{settings.HF_SPACE_E_COMMERCE_URL}/commerce_shop/cod_store_confirmed/"
			logger.info(f"[confirm_store] 準備通知商城,URL={notify_url}")  # 【新增】先印出實際要打的網址
			
			try:
				response = httpx.post(
					f"{settings.HF_SPACE_E_COMMERCE_URL}/commerce_shop/cod_store_confirmed/",
					json=notify_payload,
					timeout=10,
				)
				# 【新增】不管成功與否,先把完整回應內容印出來
				logger.info(f"[confirm_store] 商城回應: status={response.status_code}, body={response.text}")
			except httpx.HTTPError as e:
				# 連線失敗、逾時等 httpx 層級的例外,一律視為通知失敗,
				# 拋出 ShopNotifyError 讓外層的 transaction.atomic() 據此 rollback
				raise ShopNotifyError(f"連線商城失敗: {type(e).__name__}: {e}") from e

			if response.status_code != 200:
				# 商城收到請求但處理失敗(例如商城那邊找不到訂單、簽章不符、DB 寫入錯誤),
				# 一樣視為通知失敗,把商城回傳內容原封不動記下來方便除錯
				raise ShopNotifyError(
					f"商城回應非 200: status={response.status_code}, body={response.text}"
				)

	except ShopNotifyError as e:
		# 【新增】通知商城失敗,transaction.atomic() 已經自動把 cod_payment.save()
		# 一併 rollback,這裡只需要記錄錯誤、回應清楚的錯誤頁面給使用者
		logger.exception(f"[confirm_store.notify_shop_failed] 訂單 {merchant_trade_no} 通知商城失敗")
		return render(
			request,
			"cod_error.html",
			{
				"error_message": "通知商城失敗,您選擇的門市尚未確認成功,請返回商店訂單頁面重新操作。",
				"merchant_trade_no": merchant_trade_no,
				"HF_SPACE_E_COMMERCE_URL": settings.HF_SPACE_E_COMMERCE_URL,
			},
			status=502,	 # 502 Bad Gateway:代表上游(商城)服務通知失敗
		)
	except Exception as e:
		# 保底:寫入 DB 階段本身出現非預期例外(跟通知商城無關),一樣要 rollback + 記錄
		logger.exception(f"[confirm_store.db_write_unexpected] 訂單 {merchant_trade_no} 寫入失敗")
		return render(
			request,
			"cod_error.html",
			{
				"error_message": "系統發生錯誤,門市確認失敗,請返回商店訂單頁面重新操作。",
				"merchant_trade_no": merchant_trade_no,
				"HF_SPACE_E_COMMERCE_URL": settings.HF_SPACE_E_COMMERCE_URL,
			},
			status=500,
		)

	try:
		del request.session["cod_merchant_trade_no"]
	except KeyError:
		pass

	context = {"cod": cod_payment, "HF_SPACE_E_COMMERCE_URL": settings.HF_SPACE_E_COMMERCE_URL}
	return render(request, "cod_info.html", context)

def review_store(request):
	"""
	【新增】選店後的「確認頁」:
	使用者在地圖頁選好門市、按下「確認選擇此門市」後,先導到這一頁,
	讓他們可以再看一次資訊、決定要不要送出——這裡刻意「不寫入任何資料庫紀錄」,
	純粹顯示使用者選的門市 + 訂單資訊,所以就算使用者在這頁按上一頁、
	或直接關掉分頁,CODPaymentRequest 都還維持在尚未確認門市的狀態,不會留下半套資料。
	真正寫入 DB + 通知商城,要等使用者在這頁再按一次「確認送出」才會呼叫 confirm_store。
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
		return _log_and_build_error_response("review_store.validate_input", e, status=400)
	except Exception as e:
		return _log_and_build_error_response("review_store.validate_input_unexpected", e, status=500)

	try:
		cod_payment = CODPaymentRequest.objects.get(merchant_trade_no=merchant_trade_no)
	except CODPaymentRequest.DoesNotExist as e:
		return _log_and_build_error_response("review_store.cod_payment_not_found", e, status=404)
	except Exception as e:
		return _log_and_build_error_response("review_store.db_read_unexpected", e, status=500)

	context = {
		"store": store,
		"cod_payment": cod_payment,
		"merchant_trade_no": merchant_trade_no,
		"HF_SPACE_E_COMMERCE_URL": settings.HF_SPACE_E_COMMERCE_URL,
	}
	return render(request, "review_store.html", context)

@csrf_exempt
def simulate_shipped(request, merchant_trade_no):
    """
    【新增】模擬:貨物已送達超商(demo 用,沒有真的物流串接,由人工按鈕觸發)。
    只更新 CODPaymentRequest.status: cod_created → cod_shipped。
    這一步不需要通知商城(商城端目前只在乎「待處理」vs「已付款」,不細分配送中),
    純粹是讓 cod_gateway 這邊的狀態機走完整個流程,方便你之後想在商城端顯示
    更細的物流狀態時,資料已經現成可以接上。
    """
    if request.method != "POST":
        return HttpResponse("method error", status=405)

    try:
        cod_payment = CODPaymentRequest.objects.get(merchant_trade_no=merchant_trade_no)
    except CODPaymentRequest.DoesNotExist as e:
        return _log_and_build_error_response("simulate_shipped.not_found", e, status=404)
    except Exception as e:
        return _log_and_build_error_response("simulate_shipped.db_read_unexpected", e, status=500)

    # 防呆:只有「待出貨」狀態才能模擬出貨,避免重複點擊/瀏覽器返回上一頁重送
    # 造成狀態被錯誤地從 cod_paid 又打回 cod_shipped
    if cod_payment.status != "cod_created":
        logger.warning(
            f"[simulate_shipped] 訂單 {merchant_trade_no} 目前狀態是 "
            f"{cod_payment.status},不是 cod_created,略過這次模擬,直接顯示現況"
        )
        context = {"cod": cod_payment, "HF_SPACE_E_COMMERCE_URL": settings.HF_SPACE_E_COMMERCE_URL}
        return render(request, "cod_info.html", context)

    try:
        cod_payment.status = "cod_shipped"
        cod_payment.shipped_at = timezone.now()
        cod_payment.save()
    except Exception as e:
        return _log_and_build_error_response("simulate_shipped.db_write", e, status=500)

    logger.info(f"[simulate_shipped] 訂單 {merchant_trade_no} 已模擬「貨已送達超商」")
    context = {"cod": cod_payment, "HF_SPACE_E_COMMERCE_URL": settings.HF_SPACE_E_COMMERCE_URL}
    return render(request, "cod_info.html", context)


@csrf_exempt
def simulate_cod_paid(request, merchant_trade_no):
    """
    【新增】模擬:顧客到店取貨並付現(demo 用,人工按鈕觸發,取代真實物流/收銀系統通知)。
    做兩件事,包在同一個 transaction.atomic() 裡,確保一致性(跟 confirm_store 同一套設計):
    1. 更新 CODPaymentRequest.status → cod_paid
    2. httpx 通知商城(E_commerce)「這筆 COD 訂單已完成付款」
       只要通知商城失敗(連線失敗或商城回應非 200),整個 rollback,
       不會出現「cod_gateway 覺得已付款,商城卻不知道」的資料不一致。
    """
    if request.method != "POST":
        return HttpResponse("method error", status=405)

    try:
        cod_payment = CODPaymentRequest.objects.get(merchant_trade_no=merchant_trade_no)
    except CODPaymentRequest.DoesNotExist as e:
        return _log_and_build_error_response("simulate_cod_paid.not_found", e, status=404)
    except Exception as e:
        return _log_and_build_error_response("simulate_cod_paid.db_read_unexpected", e, status=500)

    # 冪等處理:已經付款完成的訂單,重複點擊直接顯示既有結果,不當錯誤處理
    if cod_payment.status == "cod_paid":
        logger.info(f"[simulate_cod_paid] 訂單 {merchant_trade_no} 已經是付款完成狀態,直接顯示既有結果")
        context = {"cod": cod_payment, "HF_SPACE_E_COMMERCE_URL": settings.HF_SPACE_E_COMMERCE_URL}
        return render(request, "cod_info.html", context)

    # 防呆:必須先出貨才能模擬取貨付款,避免狀態機跳步
    if cod_payment.status != "cod_shipped":
        logger.warning(
            f"[simulate_cod_paid] 訂單 {merchant_trade_no} 目前狀態是 "
            f"{cod_payment.status},尚未出貨,無法模擬取貨付款"
        )
        return render(request, "cod_error.html", {
            "error_message": "這筆訂單尚未出貨,請先模擬「貨已送達超商」。",
            "merchant_trade_no": merchant_trade_no,
            "HF_SPACE_E_COMMERCE_URL": settings.HF_SPACE_E_COMMERCE_URL,
        }, status=400)

    try:
        with transaction.atomic():
            cod_payment.status = "cod_paid"
            cod_payment.paid_at = timezone.now()
            cod_payment.save()

            notify_payload = {
                "merchant_trade_no": cod_payment.merchant_trade_no,
                "trade_amt": str(cod_payment.trade_amt),
                "transaction_id": str(uuid.uuid4()),
            }
            notify_payload["check_mac_value"] = generate_check_mac_value(
                notify_payload, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV
            )
            notify_url = f"{settings.HF_SPACE_E_COMMERCE_URL}/commerce_shop/cod_payment_confirmed/"
            logger.info(f"[simulate_cod_paid] 準備通知商城,URL={notify_url}")

            try:
                response = httpx.post(notify_url, json=notify_payload, timeout=10)
                logger.info(f"[simulate_cod_paid] 商城回應: status={response.status_code}, body={response.text}")
            except httpx.HTTPError as e:
                raise ShopNotifyError(f"連線商城失敗: {type(e).__name__}: {e}") from e

            if response.status_code != 200:
                raise ShopNotifyError(
                    f"商城回應非 200: status={response.status_code}, body={response.text}"
                )

    except ShopNotifyError as e:
        logger.exception(f"[simulate_cod_paid.notify_shop_failed] 訂單 {merchant_trade_no} 通知商城失敗")
        return render(request, "cod_error.html", {
            "error_message": "通知商城付款結果失敗,請稍後再試一次「模擬取貨付款」。",
            "merchant_trade_no": merchant_trade_no,
            "HF_SPACE_E_COMMERCE_URL": settings.HF_SPACE_E_COMMERCE_URL,
        }, status=502)
    except Exception as e:
        logger.exception(f"[simulate_cod_paid.db_write_unexpected] 訂單 {merchant_trade_no} 寫入失敗")
        return render(request, "cod_error.html", {
            "error_message": "系統發生錯誤,模擬付款失敗,請稍後再試。",
            "merchant_trade_no": merchant_trade_no,
            "HF_SPACE_E_COMMERCE_URL": settings.HF_SPACE_E_COMMERCE_URL,
        }, status=500)

    logger.info(f"[simulate_cod_paid] 訂單 {merchant_trade_no} 已模擬「顧客取貨付款」完成")
    context = {"cod": cod_payment, "HF_SPACE_E_COMMERCE_URL": settings.HF_SPACE_E_COMMERCE_URL}
    return render(request, "cod_info.html", context)

# @csrf_exempt
# def confirm_store(request):
	# """
	# 使用者在確認頁按下「確認送出」後,真正把門市資訊寫進 CODPaymentRequest,
	# 並用 httpx 通知商城(E_commerce)這筆訂單已確認超商取貨付款。

	# 【修改】原本「通知商城失敗只印錯誤、不影響使用者看到確認頁」的邏輯是錯的——
	# 這樣會讓 ecpay_mock 和 E_commerce 兩邊資料不一致。改成:
	# 門市寫入 + 通知商城 一起包進同一個 transaction.atomic(),
	# 只要通知商城失敗(連線錯誤,或商城回應非 200),就拋出 ShopNotifyError,
	# 讓這次的門市寫入也跟著 rollback,並回應清楚的錯誤頁面,
	# 附上返回商店訂單頁面的按鈕,讓使用者可以重新操作。
	# """
	# if request.method != "POST":
		# return HttpResponse("method error", status=405)

	# try:
		# merchant_trade_no = request.session.get("cod_merchant_trade_no")
		# if not merchant_trade_no:
			# raise ValueError("session 已遺失,找不到對應訂單,請重新從商城結帳")

		# store_id = request.POST.get("store_id")
		# store = next((s for s in MOCK_STORES if s["store_id"] == store_id), None)
		# if not store:
			# raise ValueError(f"門市代號 '{store_id}' 不存在,請重新選擇")

	# except ValueError as e:
		# return _log_and_build_error_response("confirm_store.validate_input", e, status=400)
	# except Exception as e:
		# return _log_and_build_error_response("confirm_store.validate_input_unexpected", e, status=500)

	# try:
		# cod_payment = CODPaymentRequest.objects.get(merchant_trade_no=merchant_trade_no)
	# except CODPaymentRequest.DoesNotExist as e:
		# return _log_and_build_error_response("confirm_store.cod_payment_not_found", e, status=404)
	# except Exception as e:
		# return _log_and_build_error_response("confirm_store.db_read_unexpected", e, status=500)

	# # 防止同一筆訂單被重複確認門市(連點兩次、瀏覽器返回上一頁重送)——這段不變動
	# if cod_payment.store_id:
		# logger.info(f"[confirm_store] 訂單 {merchant_trade_no} 已確認過門市,直接顯示既有結果")
		# try:
			# del request.session["cod_merchant_trade_no"]
		# except KeyError:
			# pass
		# context = {"cod": cod_payment, "HF_SPACE_E_COMMERCE_URL": settings.HF_SPACE_E_COMMERCE_URL}
		# return render(request, "cod_info.html", context)

	# # ── 【修改】門市寫入 + 通知商城,包進同一個 transaction.atomic() ──────
	# # 只要通知商城失敗,整個區塊(包含 cod_payment.save())都會自動 rollback,
	# # 不會留下「ecpay_mock 已確認,商城不知道」的不一致狀態。
	# try:
		# with transaction.atomic():
			# cod_payment.logistics_subtype = store["chain"]
			# cod_payment.store_id = store["store_id"]
			# cod_payment.store_name = store["name"]
			# cod_payment.store_address = store["address"]
			# cod_payment.store_lat = store["lat"]
			# cod_payment.store_lng = store["lng"]
			# cod_payment.save()

			# notify_payload = {
				# "merchant_trade_no": cod_payment.merchant_trade_no,
				# "store_name": cod_payment.store_name,
				# "store_address": cod_payment.store_address,
				# "logistics_subtype": cod_payment.logistics_subtype,
			# }
			# notify_payload["check_mac_value"] = generate_check_mac_value(
				# notify_payload, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV
			# )

			# try:
				# response = httpx.post(
					# f"{settings.HF_SPACE_E_COMMERCE_URL}/commerce_shop/cod_store_confirmed/",
					# json=notify_payload,
					# timeout=10,
				# )
			# except httpx.HTTPError as e:
				# # 連線失敗、逾時等 httpx 層級的例外,一律視為通知失敗,
				# # 拋出 ShopNotifyError 讓外層的 transaction.atomic() 據此 rollback
				# raise ShopNotifyError(f"連線商城失敗: {type(e).__name__}: {e}") from e

			# if response.status_code != 200:
				# # 商城收到請求但處理失敗(例如商城那邊找不到訂單、簽章不符、DB 寫入錯誤),
				# # 一樣視為通知失敗,把商城回傳內容原封不動記下來方便除錯
				# raise ShopNotifyError(
					# f"商城回應非 200: status={response.status_code}, body={response.text}"
				# )

	# except ShopNotifyError as e:
		# # 【新增】通知商城失敗,transaction.atomic() 已經自動把 cod_payment.save()
		# # 一併 rollback,這裡只需要記錄錯誤、回應清楚的錯誤頁面給使用者
		# logger.exception(f"[confirm_store.notify_shop_failed] 訂單 {merchant_trade_no} 通知商城失敗")
		# return render(
			# request,
			# "cod_error.html",
			# {
				# "error_message": "通知商城失敗,您選擇的門市尚未確認成功,請返回商店訂單頁面重新操作。",
				# "merchant_trade_no": merchant_trade_no,
				# "HF_SPACE_E_COMMERCE_URL": settings.HF_SPACE_E_COMMERCE_URL,
			# },
			# status=502,	 # 502 Bad Gateway:代表上游(商城)服務通知失敗
		# )
	# except Exception as e:
		# # 保底:寫入 DB 階段本身出現非預期例外(跟通知商城無關),一樣要 rollback + 記錄
		# logger.exception(f"[confirm_store.db_write_unexpected] 訂單 {merchant_trade_no} 寫入失敗")
		# return render(
			# request,
			# "cod_error.html",
			# {
				# "error_message": "系統發生錯誤,門市確認失敗,請返回商店訂單頁面重新操作。",
				# "merchant_trade_no": merchant_trade_no,
				# "HF_SPACE_E_COMMERCE_URL": settings.HF_SPACE_E_COMMERCE_URL,
			# },
			# status=500,
		# )

	# try:
		# del request.session["cod_merchant_trade_no"]
	# except KeyError:
		# pass

	# context = {"cod": cod_payment, "HF_SPACE_E_COMMERCE_URL": settings.HF_SPACE_E_COMMERCE_URL}
	# return render(request, "cod_info.html", context)