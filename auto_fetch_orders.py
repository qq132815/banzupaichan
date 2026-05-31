# -*- coding: utf-8 -*-
"""Auto-import work orders from MES (only in-progress)."""
import os, time, json, sqlite3, re
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
    """Scrape all work order rows from the MES page."""
    all_rows = []
    
    # Get total pages from pagination
    pag_info = page.evaluate("""() => {
        let el = document.querySelector('[class*=pagination]');
        return el ? el.innerText : '';
    }""")
    
    total_pages = 1
    m = re.search(r'\u5171\s*(\d+)\s*\u9875', pag_info)
    if m:
        total_pages = int(m.group(1))
    else:
        m = re.search(r'(\d+)\u9875', pag_info)
        if m:
            total_pages = int(m.group(1))
    
    print("  Total pages: %d" % total_pages)
    
    for pg in range(total_pages):
        if pg > 0:
            try:
                # Click next page button (the one without 'dis' class)
                page.evaluate("""() => {
                    let btns = document.querySelectorAll('[class*="page-bottom"]');
                    for (let b of btns) {
                        if (!b.className.includes('dis')) {
                            b.click();
                            return true;
                        }
                    }
                    // Try next button
                    let next = document.querySelector('[class*="next"]:not([class*="dis"])');
                    if (next) { next.click(); return true; }
                    return false;
                }""")
                time.sleep(1.5)
            except:
                break
        
        # Extract current page rows
        rows = page.evaluate("""() => {
            let result = [];
            let trs = document.querySelectorAll('tbody tr');
            trs.forEach(tr => {
                let tds = tr.querySelectorAll('td');
                let row = [];
                tds.forEach(td => row.push(td.innerText.trim()));
                if (row.length > 1) result.push(row);
            });
            return result;
        }""")
        
        all_rows.extend(rows)
        if (pg + 1) % 10 == 0:
            print("  Page %d/%d, rows: %d" % (pg + 1, total_pages, len(all_rows)))
    
    print("  Total scraped: %d rows" % len(all_rows))
    return all_rows


def import_work_orders(rows):
    """Import scraped rows into database. Only '执行中' orders."""
    conn = get_connection()
    c = conn.cursor()
    
    for col in ['process_progress', 'source', 'route_code']:
        try:
            c.execute("ALTER TABLE work_orders ADD COLUMN %s TEXT" % col)
        except:
            pass
    
    # Column mapping (from header analysis):
    # 0: checkbox, 1: order_no, 2: sub_order_count, 3: completed_sub_orders
    # 4: status, 5: quantity, 6: completed_qty, 7: progress%
    # 8: related_doc, 9: doc_progress%, 10: creator, 11: create_time
    
    inserted = updated = skipped = 0
    for row in rows:
        if len(row) < 6:
            continue
        
        order_no = row[1] if len(row) > 1 else ''
        if not order_no or len(order_no) < 3:
            continue
        
        status = row[4] if len(row) > 4 else ''
        
        # Only import "执行中" (in progress) orders
        if '\u6267\u884c\u4e2d' not in status:
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
        
        due_date = ''
        priority = 'P2'
        product_code = ''
        product_name = ''
        
        # Check if exists
        c.execute("SELECT id FROM work_orders WHERE order_no=?", (order_no,))
        existing = c.fetchone()
        if existing:
            c.execute("""UPDATE work_orders SET quantity=?, completed_qty=?, status=? WHERE order_no=?""",
                     (quantity, completed_qty, status, order_no))
            updated += 1
        else:
            c.execute("""INSERT INTO work_orders (order_no, product_code, product_name, quantity,
                        completed_qty, due_date, priority, status) VALUES (?,?,?,?,?,?,?,?)""",
                     (order_no, product_code, product_name, quantity, completed_qty, due_date, priority, status))
            inserted += 1
    
    conn.commit()
    conn.close()
    return inserted, updated, skipped


def run_fetch_orders():
    print("[%s] Fetching work orders..." % datetime.now().strftime("%H:%M:%S"))
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        
        try:
            # Login
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
            
            # Navigate to work orders
            page.locator(u"text=\u751f\u4ea7").first.click()
            time.sleep(1)
            page.locator(u"text=\u5de5\u5355").first.click()
            time.sleep(5)
            print("  Work order page loaded")
            
            # Scrape all pages
            rows = scrape_all_pages(page)
            
            # Import
            inserted, updated, skipped = import_work_orders(rows)
            print("  Result: %d inserted, %d updated, %d skipped" % (inserted, updated, skipped))
            
        except Exception as e:
            print("Error: %s" % e)
            import traceback
            traceback.print_exc()
        finally:
            browser.close()


if __name__ == "__main__":
    run_fetch_orders()
