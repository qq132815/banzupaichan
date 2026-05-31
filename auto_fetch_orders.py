# -*- coding: utf-8 -*-
"""Auto-import work orders with process progress from MES."""
import os, time, json, sqlite3, re, sys
from datetime import datetime
from playwright.sync_api import sync_playwright

MES_URL = "https://web.ycmes.cn/"
FACTORY_CODE = "606999"
USERNAME = "GS-001"
PASSWORD = "675726"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "production.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def scrape_all_pages(page):
    all_rows = []
    pag_info = page.evaluate("() => { let el = document.querySelector('[class*=pagination]'); return el ? el.innerText : ''; }")
    total_pages = 1
    m = re.search(r'\u5171\s*(\d+)\s*\u9875', pag_info)
    if m:
        total_pages = int(m.group(1))
    print("  Total pages: %d" % total_pages)
    
    for pg in range(total_pages):
        if pg > 0:
            try:
                page.evaluate("""() => {
                    let btns = document.querySelectorAll('[class*="page-bottom"]');
                    for (let b of btns) { if (!b.className.includes('dis')) { b.click(); return; } }
                    let next = document.querySelector('[class*="next"]:not([class*="dis"])');
                    if (next) next.click();
                }""")
                time.sleep(1.5)
            except:
                break
        rows = page.evaluate("""() => {
            let result = [];
            document.querySelectorAll('tbody tr').forEach(tr => {
                let row = [];
                tr.querySelectorAll('td').forEach(td => row.push(td.innerText.trim()));
                if (row.length > 1) result.push(row);
            });
            return result;
        }""")
        all_rows.extend(rows)
        if (pg + 1) % 10 == 0:
            print("  Page %d/%d, rows: %d" % (pg + 1, total_pages, len(all_rows)))
    print("  Scraped %d rows" % len(all_rows))
    return all_rows


    """Click view on an order and scrape product+process detail."""
    try:
        # Click the view link for this order
        view_link = page.locator(u"text=\u67e5\u770b").first
        if not view_link:
            return None
        view_link.click()
        time.sleep(2)
        
        # Extract detail data
        detail = page.evaluate("""() => {
            let text = document.body.innerText;
            let products = [];
            
            // Find the detail table rows
            let tables = document.querySelectorAll('table');
            let detailTable = null;
            for (let t of tables) {
                if (t.innerText.includes('BOM\u5c42\u7ea7') || t.innerText.includes('\u5de5\u5355\u8fdb\u5ea6')) {
                    detailTable = t;
                    break;
                }
            }
            
            if (detailTable) {
                let trs = detailTable.querySelectorAll('tbody tr');
                trs.forEach(tr => {
                    let tds = tr.querySelectorAll('td');
                    let row = [];
                    tds.forEach(td => row.push(td.innerText.trim()));
                    if (row.length > 3) products.push(row);
                });
            }
            return {products: products, text: text.substring(0, 3000)};
        }""")
        
        # Close the detail popup
        try:
            close_btn = page.locator(u"text=\u5173\u95ed").first
            if close_btn:
                close_btn.click()
                time.sleep(0.5)
        except:
            page.keyboard.press("Escape")
            time.sleep(0.5)
        
        return detail
    except Exception as e:
        return None

def parse_process_progress(detail_text):
    if not detail_text:
        return ''
    processes = []
    for m in re.finditer(r'([^\n\u3010\u3011\uff08\uff09]+?)\u3010(\d+)/(\d+)\u3011[\uff08(](\d+%)[\uff09)]', detail_text):
        name = m.group(1).strip()
        if name and len(name) < 30:
            processes.append('%s[%s/%s](%s)' % (name, m.group(2), m.group(3), m.group(4)))
    if not processes:
        for m in re.finditer(r'([\u4e00-\u9fff\uff08\uff09\w]{2,20})\s+(\d+)%', detail_text):
            name = m.group(1).strip()
            if name and len(name) >= 2:
                processes.append('%s(%s%%)' % (name, m.group(2)))
    return '->'.join(processes)

def parse_product_info(detail_text):
    product_code = ''
    product_name = ''
    m = re.search(r'\u4ea7\u54c1[\u7f16\u540d\u79f0]*[\uff1a:]\s*([^\n\s]+)', detail_text)
    if m:
        product_code = m.group(1).strip()
    m = re.search(r'\u4ea7\u54c1\u540d\u79f0[\uff1a:]\s*([^\n]+)', detail_text)
    if m:
        product_name = m.group(1).strip()
    return product_code, product_name


def import_work_orders(rows, detail_map=None):
    conn = get_connection()
    c = conn.cursor()
    for col in ['process_progress', 'source', 'route_code']:
        try:
            c.execute("ALTER TABLE work_orders ADD COLUMN %s TEXT" % col)
        except:
            pass
    
    inserted = updated = skipped = 0
    detail_map = detail_map or {}
    for _idx, row in enumerate(rows):
        if len(row) < 6:
            continue
        order_no = row[1] if len(row) > 1 else ''
        if not order_no or len(order_no) < 3:
            continue
        status = row[4] if len(row) > 4 else ''
        if '执行中' not in status:
            skipped += 1
            continue
        
        try:
            quantity = float(row[5]) if len(row) > 5 and row[5] else 0
        except:
            quantity = 0
        try:
            completed_qty = float(row[6]) if len(row) > 6 and row[6] else 0
        except:
            completed_qty = 0
        
        detail = detail_map.get(_idx, {})
        product_code = detail.get('product_code', '')
        product_name = detail.get('product_name', '')
        process_progress = detail.get('process_progress', '')
        
        c.execute("SELECT id, product_code, product_name FROM work_orders WHERE order_no=?", (order_no,))
        existing = c.fetchone()
        if existing:
            final_code = product_code if product_code else (existing['product_code'] or '')
            final_name = product_name if product_name else (existing['product_name'] or '')
            if process_progress:
                c.execute("UPDATE work_orders SET quantity=?, completed_qty=?, status=?, product_code=?, product_name=?, process_progress=? WHERE order_no=?",
                    (quantity, completed_qty, status, final_code, final_name, process_progress, order_no))
            else:
                c.execute("UPDATE work_orders SET quantity=?, completed_qty=?, status=?, product_code=?, product_name=? WHERE order_no=?",
                    (quantity, completed_qty, status, final_code, final_name, order_no))
            updated += 1
        else:
            c.execute("INSERT INTO work_orders (order_no, product_code, product_name, quantity, completed_qty, due_date, priority, status, process_progress, source) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (order_no, product_code, product_name, quantity, completed_qty, '', 'P2', status, process_progress, 'mes'))
            inserted += 1
    
    conn.commit()
    conn.close()
    return inserted, updated, skipped

def run_fetch_orders(with_detail=False):
    print("[%s] Fetching work orders (detail=%s)..." % (datetime.now().strftime("%H:%M:%S"), with_detail))
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        
        try:
            for _attempt in range(3):
                try:
                    page.goto(MES_URL, wait_until="networkidle", timeout=60000)
                    break
                except:
                    if _attempt == 2: raise
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
            
            page.locator(u"text=\u751f\u4ea7").first.click()
            time.sleep(1)
            page.locator(u"text=\u5de5\u5355").first.click()
            time.sleep(5)
            print("  Page loaded")
            
            rows = scrape_all_pages(page)
            
            detail_map = {}
            if with_detail:
                print("  Scraping process progress for in-progress orders...")
                detail_count = 0
                for idx, row in enumerate(rows):
                    if len(row) < 5:
                        continue
                    status = row[4] if len(row) > 4 else ''
                    if '执行中' not in status and '进行中' not in status:
                        continue
                    detail_text = scrape_order_detail(page, idx)
                    if detail_text:
                        pp = parse_process_progress(detail_text)
                        pc, pn = parse_product_info(detail_text)
                        detail_map[idx] = {'product_code': pc, 'product_name': pn, 'process_progress': pp}
                        detail_count += 1
                        if detail_count % 5 == 0:
                            print("  Detail %d done" % detail_count)
                    time.sleep(0.5)
                print("  Scraped %d order details" % detail_count)
            
            inserted, updated, skipped = import_work_orders(rows, detail_map)
            print("  Result: %d inserted, %d updated, %d skipped" % (inserted, updated, skipped))
            
        except Exception as e:
            print("Error: %s" % e)
            import traceback
            traceback.print_exc()
        finally:
            browser.close()


if __name__ == "__main__":
    import sys as _sys
    run_fetch_orders(with_detail=('--detail' in _sys.argv))
