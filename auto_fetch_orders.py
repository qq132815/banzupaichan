# -*- coding: utf-8 -*-
"""Auto-import work orders from MES via export download."""
import os, sys, time, sqlite3
from datetime import datetime

MES_URL = "https://web.ycmes.cn/"
FACTORY_CODE = "606999"
USERNAME = "GS-001"
PASSWORD = "675726"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
DB_PATH = os.path.join(BASE_DIR, "data", "production.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def import_work_orders_from_excel(filepath):
    """Import work orders from MES exported Excel file."""
    import openpyxl
    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb.active

    # Row 1 may be merged title, Row 2 is headers, Row 3+ is data
    # Detect header row by looking for known column names
    headers = []
    header_row = 1
    for row_idx in range(1, 4):
        row_vals = [str(c.value or "").strip() for c in ws[row_idx]]
        joined = "|".join(row_vals)
        if any(k in joined for k in ["工单编号", "装配工单", "计划数", "工单状态"]):
            headers = row_vals
            header_row = row_idx
            break

    if not headers:
        # Fallback: assume row 1 is headers
        headers = [str(c.value or "").strip() for c in ws[1]]
        header_row = 1

    # Build column mapping
    col_map = {}
    field_aliases = {
        "order_no": ["工单编号", "装配工单编号", "工单号", "订单编号"],
        "product_code": ["产品编号", "产品编码", "件号"],
        "product_name": ["产品名称", "产品图", "品名"],
        "status": ["工单状态", "状态", "单据状态"],
        "process_progress": ["工单进度条", "工序进度", "进度条", "生产进度"],
        "quantity": ["计划数", "数量", "计划数量", "工单数"],
        "priority": ["优先级"],
        "due_date": ["计划结束时间", "交期", "截止日期", "完工日期"],
        "completed_qty": ["完工数", "完成数", "已完工数", "已结束工单数"],
        "source": ["产品来源", "来源"],
    }

    for field, aliases in field_aliases.items():
        for i, h in enumerate(headers):
            if h in aliases:
                col_map[field] = i
                break

    if "order_no" not in col_map:
        print("  ERROR: Cannot find order_no column in headers: %s" % headers)
        wb.close()
        return 0, 0

    conn = get_connection()
    c = conn.cursor()
    for col in ["process_progress", "source", "route_code"]:
        try:
            c.execute("ALTER TABLE work_orders ADD COLUMN %s TEXT" % col)
        except:
            pass

    inserted = updated = skipped = 0

    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        if not row or not any(row):
            continue

        order_no_idx = col_map.get("order_no", -1)
        if order_no_idx >= len(row) or not row[order_no_idx]:
            continue
        order_no = str(row[order_no_idx]).strip()
        if not order_no or len(order_no) < 3:
            continue

        # Parse fields
        def get_val(field, default=""):
            idx = col_map.get(field, -1)
            if idx >= 0 and idx < len(row) and row[idx] is not None:
                return str(row[idx]).strip()
            return default

        def get_num(field, default=0):
            idx = col_map.get(field, -1)
            if idx >= 0 and idx < len(row) and row[idx] is not None:
                try:
                    return float(row[idx])
                except:
                    pass
            return default

        status = get_val("status", "pending")
        product_code = get_val("product_code")
        product_name = get_val("product_name")
        if not product_name:
            product_name = product_code
        quantity = get_num("quantity", 0)
        completed_qty = get_num("completed_qty", 0)
        due_date = get_val("due_date")
        if due_date:
            due_date = due_date[:10]
        priority = get_val("priority", "P2")
        process_progress = get_val("process_progress")
        source = get_val("source", "mes")

        # Check existing
        c.execute("SELECT id FROM work_orders WHERE order_no=?", (order_no,))
        existing = c.fetchone()

        if existing:
            c.execute("""UPDATE work_orders SET product_code=?, product_name=?, quantity=?,
                completed_qty=?, due_date=?, priority=?, status=?, process_progress=?, source=? WHERE order_no=?""",
                (product_code, product_name, quantity, completed_qty, due_date, priority, status, process_progress, source, order_no))
            updated += 1
        else:
            c.execute("""INSERT INTO work_orders
                (order_no, product_code, product_name, quantity, completed_qty, due_date, priority, status, process_progress, source)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (order_no, product_code, product_name, quantity, completed_qty, due_date, priority, status, process_progress, source))
            inserted += 1

    conn.commit()
    conn.close()
    wb.close()
    return inserted, updated


def run_fetch_orders():
    """Login to MES, export work orders Excel, download and import."""
    print("[%s] Fetching work orders from MES..." % datetime.now().strftime("%H:%M:%S"))

    from playwright.sync_api import sync_playwright

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(accept_downloads=True)
        page = ctx.new_page()

        try:
            # Login
            for attempt in range(3):
                try:
                    page.goto(MES_URL, wait_until="networkidle", timeout=60000)
                    break
                except:
                    if attempt == 2:
                        raise
                    time.sleep(10)
            time.sleep(2)

            page.locator(u"text=\u8d26\u53f7\u767b\u5f55").first.click()
            time.sleep(1)
            page.locator(u"input[placeholder*=\u5de5\u5382]").first.fill(FACTORY_CODE)
            page.locator(u"input[placeholder*=\u7528\u6237\u540d]").first.fill(USERNAME)
            page.locator("input[type=password]").first.fill(PASSWORD)
            page.locator("button").filter(has_text=u"\u767b\u5f55").first.click()
            page.wait_for_load_state("networkidle", timeout=30000)
            time.sleep(3)
            print("  Login OK")

            # Navigate to work order page
            page.locator(u"text=\u751f\u4ea7").first.click()
            time.sleep(1)
            page.locator(u"text=\u5de5\u5355").first.click()
            time.sleep(5)
            print("  Work order page loaded")

            # Click export button and capture download
            print("  Exporting...")
            with page.expect_download(timeout=180000) as dl_info:
                btns = page.locator("button").all()
                for btn in btns:
                    try:
                        txt = btn.text_content() or ""
                        if u"\u5bfc\u51fa" in txt:
                            btn.click()
                            print("  Clicked export button")
                            break
                    except:
                        pass

            download = dl_info.value
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(DOWNLOAD_DIR, "work_orders_%s.xlsx" % ts)
            download.save_as(filepath)
            print("  Downloaded: %s" % filepath)

            # Import into database
            inserted, updated = import_work_orders_from_excel(filepath)
            print("  Imported: %d new, %d updated" % (inserted, updated))

            # Cleanup old files (keep last 3)
            try:
                files = sorted([f for f in os.listdir(DOWNLOAD_DIR)
                    if f.startswith("work_orders_") and f.endswith(".xlsx")])
                for old in files[:-3]:
                    os.remove(os.path.join(DOWNLOAD_DIR, old))
            except:
                pass

        except Exception as e:
            print("Error: %s" % e)
            import traceback
            traceback.print_exc()
            try:
                page.screenshot(path=os.path.join(DOWNLOAD_DIR, "wo_export_error.png"))
            except:
                pass
        finally:
            browser.close()


if __name__ == "__main__":
    run_fetch_orders()
