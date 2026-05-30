# -*- coding: utf-8 -*-
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db import get_connection

def calculate_alerts():
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM alerts")
    today = datetime.now().date()
    c.execute("SELECT sp.product_code, sp.quantity, sp.ship_date FROM shipping_plan sp")
    plans = c.fetchall()
    for plan in plans:
        product_code = plan[0]
        quantity = plan[1]
        ship_date = datetime.strptime(plan[2], '%Y-%m-%d').date() if plan[2] else today
        days_remaining = (ship_date - today).days
        c.execute("SELECT COALESCE(SUM(quantity), 0) FROM schedules WHERE work_order_no IN (SELECT order_no FROM work_orders WHERE product_code=?) AND task_status != ?", (product_code, 'cancelled'))
        scheduled_qty = c.fetchone()[0] or 0
        shortage = quantity - scheduled_qty
        if days_remaining <= 3 and shortage > 0:
            level = 'red'
        elif days_remaining <= 7 and shortage > quantity * 0.5:
            level = 'yellow'
        else:
            level = 'green'
        message = product_code + ' needs ' + str(int(shortage)) + ' more, ' + str(days_remaining) + ' days left'
        c.execute("INSERT INTO alerts (product_code, alert_level, due_date, quantity, scheduled_qty, shortage_qty, days_remaining, message, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (product_code, level, plan[2], quantity, scheduled_qty, shortage, days_remaining, message, 'active'))
    conn.commit()
    count = len(plans)
    conn.close()
    return count

def back_calculate_semi():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT sp.product_code, sp.quantity, sp.ship_date FROM shipping_plan sp")
    plans = c.fetchall()
    new_orders = 0
    for plan in plans:
        product_code = plan[0]
        quantity = plan[1]
        ship_date = plan[2]
        c.execute("SELECT child_product_code, child_product_name, quantity, process_team FROM bom WHERE parent_product_code=?", (product_code,))
        children = c.fetchall()
        for child in children:
            child_code = child[0]
            child_name = child[1]
            bom_qty = child[2] if child[2] else 1
            required_qty = quantity * bom_qty
            c.execute("SELECT production_days, lead_days FROM production_cycles WHERE product_code=?", (child_code,))
            cycle = c.fetchone()
            prod_days = cycle[0] if cycle else 1
            lead_days = cycle[1] if cycle else 0
            ship_dt = datetime.strptime(ship_date, '%Y-%m-%d') if ship_date else datetime.now()
            due_dt = ship_dt - timedelta(days=lead_days)
            due_str = due_dt.strftime('%Y-%m-%d')
            order_no = 'BC-' + product_code + '-' + child_code
            c.execute("SELECT id FROM work_orders WHERE order_no=?", (order_no,))
            if not c.fetchone():
                c.execute("INSERT INTO work_orders (order_no, product_code, product_name, quantity, due_date, priority, status, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (order_no, child_code, child_name, required_qty, due_str, 'P1', 'pending', ''))
                new_orders += 1
    conn.commit()
    conn.close()
    return new_orders

def calculate_quantity(hours, capacity_per_hour):
    if hours and capacity_per_hour:
        return hours * capacity_per_hour
    return 0

def calculate_production_requirements():
    """Calculate production requirements from shipping plans using recursive BOM expansion"""
    conn = get_connection()
    c = conn.cursor()
    
    # Clear ALL existing requirements before recalculating
    c.execute("DELETE FROM production_requirements")
    
    today = datetime.now().date()
    results = []
    
    # Build cycle dictionaries
    c.execute("SELECT product_code, production_days, lead_days FROM production_cycles")
    cycle_prod = {}  # production days
    cycle_lead = {}  # lead days
    for row in c.fetchall():
        prod = row[0].strip() if row[0] else ''
        if prod:
            cycle_prod[prod] = int(row[1]) if row[1] else 1
            cycle_lead[prod] = int(row[2]) if row[2] else 0
    
    # Build BOM dictionary: parent_code -> [(child_code, child_name, unit_qty, process_team)]
    c.execute("SELECT parent_product_code, child_product_code, child_product_name, quantity, process_team FROM bom")
    bom_dict = {}
    for row in c.fetchall():
        parent = row[0].strip() if row[0] else ''
        child_code = row[1].strip() if row[1] else ''
        child_name = row[2].strip() if row[2] else ''
        qty = abs(float(row[3])) if row[3] else 1
        team = row[4].strip() if row[4] else ''
        if parent and child_code:
            if parent not in bom_dict:
                bom_dict[parent] = []
            bom_dict[parent].append((child_code, child_name, qty, team))
    
    # Get all shipping plans
    c.execute("SELECT product_code, quantity, ship_date FROM shipping_plan ORDER BY ship_date")
    plans = c.fetchall()
    
    # Recursive BOM expansion
    def expand_bom(product_code, required_qty, ship_date, level, parent_chain):
        """Recursively expand BOM and calculate requirements for ALL products"""
        if level > 10:  # Prevent infinite recursion
            return
        
        # Calculate dates for this product
        prod_days = cycle_prod.get(product_code, 1)
        lead_days = cycle_lead.get(product_code, 0)
        ship_dt = datetime.strptime(ship_date, '%Y-%m-%d').date() if isinstance(ship_date, str) else ship_date
        
        # 完成时间 = 需要交付的时间 (ship_date for level 0, parent's start for children)
        completion_date = ship_dt
        
        # 投入时间 = 完成时间 - 生产天数 - 提先天数
        start_date = completion_date - timedelta(days=prod_days + lead_days)
        
        completion_date_str = completion_date.strftime('%Y-%m-%d')
        
        # For children: they need to be completed before parent starts
        parent_start_date = start_date
        
        # Get process route for this product
        c.execute("SELECT process_list FROM process_routes WHERE product_code=?", (product_code,))
        route = c.fetchone()
        process_list = route[0] if route else ''
        
        # Determine team from process
        team_name = ''
        if process_list:
            first_process = process_list.split(',')[0].strip()
            if first_process:
                c.execute("SELECT team_name FROM processes WHERE process_name=?", (first_process,))
                proc = c.fetchone()
                if proc:
                    team_name = proc[0] or ''
        
        # Get product name - try multiple sources
        product_name = product_code
        # Try work_orders first
        c.execute("SELECT product_name FROM work_orders WHERE product_code=? LIMIT 1", (product_code,))
        wo = c.fetchone()
        if wo and wo[0] and wo[0] != product_code:
            product_name = wo[0]
        else:
            # Try BOM child name
            c.execute("SELECT child_product_name FROM bom WHERE child_product_code=? AND child_product_name != child_product_code LIMIT 1", (product_code,))
            bom_child = c.fetchone()
            if bom_child and bom_child[0]:
                product_name = bom_child[0]
            else:
                # Try BOM parent name
                c.execute("SELECT parent_product_name FROM bom WHERE parent_product_code=? AND parent_product_name != parent_product_code LIMIT 1", (product_code,))
                bom_parent = c.fetchone()
                if bom_parent and bom_parent[0]:
                    product_name = bom_parent[0]
        
        # Add this product to results (both finished and semi-finished)
        # root_product is the top-level finished product (level 0)
        root_product = parent_chain.split(' -> ')[0] if ' -> ' in parent_chain else parent_chain
        results.append({
            'product_code': product_code,
            'product_name': product_name,
            'ship_date': ship_date,
            'ship_quantity': required_qty,
            'required_date': completion_date_str,
            'required_quantity': required_qty,
            'team_name': team_name,
            'process_name': process_list,
            'level': level,
            'parent_chain': parent_chain,
            'root_product': root_product,
            'sort_key': parent_chain  # Use parent_chain for sorting
        })
        
        # Check if this product has BOM children and expand them
        # Children need to be completed BEFORE this product starts production
        children = bom_dict.get(product_code, [])
        if children:
            for child_code, child_name, unit_qty, team in children:
                child_qty = required_qty * unit_qty
                child_chain = parent_chain + ' -> ' + child_code if parent_chain else child_code
                # Pass parent's start_date as the child's "ship date"
                expand_bom(child_code, child_qty, parent_start_date.strftime('%Y-%m-%d'), level + 1, child_chain)
    
    # Process each shipping plan
    for plan in plans:
        product_code = plan[0].strip() if plan[0] else ''
        quantity = plan[1] if plan[1] else 0
        ship_date = plan[2]
        
        if not product_code or quantity <= 0 or not ship_date:
            continue
        
        # Expand BOM for this product
        expand_bom(product_code, quantity, ship_date, 0, product_code)
    
    # Deduplicate: aggregate quantities for same product + same required_date
    aggregated = {}
    for r in results:
        key = r['product_code'] + '|' + r['required_date']
        if key not in aggregated:
            aggregated[key] = dict(r)
        else:
            aggregated[key]['required_quantity'] += r['required_quantity']
            aggregated[key]['ship_quantity'] += r['ship_quantity']
    
    # Insert aggregated results into database
    for key, r in aggregated.items():
        c.execute("""INSERT INTO production_requirements 
                    (product_code, product_name, ship_date, ship_quantity, 
                     required_date, required_quantity, team_name, process_name, status, bom_level, root_product, parent_chain)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?)""",
                 (r['product_code'], r['product_name'], r['ship_date'], r['ship_quantity'],
                  r['required_date'], r['required_quantity'], r['team_name'], r['process_name'], 
                  r.get('level', 0), r.get('root_product', ''), r.get('parent_chain', '')))
    
    conn.commit()
    conn.close()
    return len(results)
def publish_requirements(requirement_ids=None):
    """Publish selected requirements or all draft requirements"""
    conn = get_connection()
    c = conn.cursor()
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    if requirement_ids:
        # Publish specific requirements
        for req_id in requirement_ids:
            c.execute("UPDATE production_requirements SET status='published', published_at=? WHERE id=? AND status='draft'", (now, req_id))
    else:
        # Publish all draft requirements
        c.execute("UPDATE production_requirements SET status='published', published_at=? WHERE status='draft'", (now,))
    
    conn.commit()
    affected = c.rowcount
    conn.close()
    return affected


def get_published_requirements(team_name=None, start_date=None, end_date=None):
    """Get published requirements for display"""
    conn = get_connection()
    c = conn.cursor()
    
    sql = "SELECT * FROM production_requirements WHERE status='published'"
    params = []
    
    if team_name:
        # Support comma-separated teams
        sql += " AND team_name LIKE ?"
        params.append('%' + team_name + '%')
    
    if start_date:
        sql += " AND required_date >= ?"
        params.append(start_date)
    
    if end_date:
        sql += " AND required_date <= ?"
        params.append(end_date)
    
    sql += " ORDER BY required_date, product_code"
    c.execute(sql, params)
    results = [dict(row) for row in c.fetchall()]
    conn.close()
    return results
