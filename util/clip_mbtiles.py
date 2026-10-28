import math
import sqlite3

SRC = "north.mbtiles"      # 原始檔
DST = "taoyuan.mbtiles"    # 輸出檔
# 桃園市大致範圍 (西, 南, 東, 北),略放寬一點避免邊緣露白
W, S, E, N = 120.95, 24.60, 121.50, 25.15

def lonlat_to_tile(lon, lat, z):
    # 經緯度 -> XYZ 圖磚座標
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    lat_r = math.radians(lat)
    y = int((1 - math.asinh(math.tan(lat_r)) / math.pi) / 2 * n)
    return x, y

src = sqlite3.connect(SRC)
dst = sqlite3.connect(DST)

# 建立 mbtiles 標準結構
dst.executescript("""
CREATE TABLE metadata (name TEXT, value TEXT);
CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER,
                    tile_row INTEGER, tile_data BLOB);
""")

# 複製 metadata,bounds / center 之後覆蓋
for name, value in src.execute("SELECT name, value FROM metadata"):
    if name not in ("bounds", "center"):
        dst.execute("INSERT INTO metadata VALUES (?, ?)", (name, value))
dst.execute("INSERT INTO metadata VALUES ('bounds', ?)", (f"{W},{S},{E},{N}",))

zooms = [r[0] for r in src.execute("SELECT DISTINCT zoom_level FROM tiles")]
for z in sorted(zooms):
    x1, y_top = lonlat_to_tile(W, N, z)      # 左上角
    x2, y_bottom = lonlat_to_tile(E, S, z)   # 右下角
    # mbtiles 的 tile_row 是 TMS(由下往上),要由 XYZ 轉換
    row_min = (2 ** z - 1) - y_bottom
    row_max = (2 ** z - 1) - y_top
    dst.execute("""
        INSERT INTO tiles
        SELECT zoom_level, tile_column, tile_row, tile_data FROM (
            SELECT * FROM tiles.tiles
        ) WHERE 0
    """) if False else None
    rows = src.execute(
        "SELECT zoom_level, tile_column, tile_row, tile_data FROM tiles "
        "WHERE zoom_level=? AND tile_column BETWEEN ? AND ? "
        "AND tile_row BETWEEN ? AND ?",
        (z, x1, x2, row_min, row_max))
    dst.executemany("INSERT INTO tiles VALUES (?,?,?,?)", rows)
    print("zoom", z, "完成")

dst.execute("CREATE UNIQUE INDEX tile_index ON tiles "
            "(zoom_level, tile_column, tile_row)")
dst.execute("CREATE UNIQUE INDEX name ON metadata (name)")
dst.commit()
dst.execute("VACUUM")   # 壓縮檔案
dst.close()