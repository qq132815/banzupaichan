# -*- coding: utf-8 -*-
import openpyxl
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db import get_connection


def import_shipping_plan(file_path):
    wb = openpyxl.load_workbook(file_path)
    ws = wb.active
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM shipping_plan")
    headers = [cell.value for cell in ws[1]]
    dates = []
    for i, h in enumerate(headers):
        if hasattr(h, 'strftime'):
            dates.append((i, h))
    count = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        product_code = str(row[0]).strip()
        for col_idx, ship_date in dates:
            qty = row[col_idx] if col_idx < len(row) else None
            if qty and str(qty).isdigit() and int(qty) > 0:
                date_str = ship_date.strftime('%Y-%m-%d')
                c.execute("INSERT INTO shipping_plan (product_code, quantity, ship_date) VALUES (?, ?, ?)",
                          (product_code, int(qty), date_str))
                count += 1
    conn.commit()
    conn.close()
    return count


def import_production_cycles(file_path):
    wb = openpyxl.load_workbook(file_path)
    ws = wb.active
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM production_cycles")
    count = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        product_code = str(row[0]).strip()
        prod_days = row[1] if row[1] else 1
        lead_days = row[2] if row[2] else 0
        c.execute("INSERT INTO production_cycles (product_code, production_days, lead_days) VALUES (?, ?, ?)",
                  (product_code, prod_days, lead_days))
        count += 1
    conn.commit()
    conn.close()
    return count


def import_work_orders(file_path):
    wb = openpyxl.load_workbook(file_path)
    ws = wb.active
    conn = get_connection()
    c = conn.cursor()
    # Ensure process_progress column exists
    try:
        c.execute("ALTER TABLE work_orders ADD COLUMN process_progress TEXT")
    except:
        pass
    count = 0
    # Row 1 = title, Row 2 = headers, Row 3+ = data
    for row in ws.iter_rows(min_row=3, values_only=True):
        if not row or not row[0]:
            continue
        order_no = str(row[0]).strip()
        product_code = str(row[2]).strip() if row[2] else ''
        product_name = str(row[2]).strip() if row[2] else ''
        quantity = row[5] if row[5] else 0
        priority = str(row[6]).strip() if row[6] else 'P2'
        due_date = row[10].strftime('%Y-%m-%d') if hasattr(row[10], 'strftime') else str(row[10]) if row[10] else None
        status = str(row[3]).strip() if len(row) > 3 and row[3] else 'pending'
        completed_qty = row[13] if len(row) > 13 and row[13] else 0
        # Col4: process progress string
        process_progress = str(row[4]).strip() if len(row) > 4 and row[4] else ''
        c.execute("INSERT OR REPLACE INTO work_orders (order_no, product_code, product_name, quantity, completed_qty, due_date, priority, status, process_progress) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  (order_no, product_code, product_name, quantity, completed_qty, due_date, priority, status, process_progress))
        count += 1
    conn.commit()
    conn.close()
    return count


def import_processes(file_path):
    wb = openpyxl.load_workbook(file_path)
    ws = wb.active
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM processes")
    count = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        process_code = str(row[0]).strip()
        process_name = str(row[1]).strip() if row[1] else ''
        team_name = str(row[2]).strip() if row[2] else None
        c.execute("INSERT OR REPLACE INTO processes (process_code, process_name, team_name) VALUES (?, ?, ?)",
                  (process_code, process_name, team_name))
        count += 1
    conn.commit()
    conn.close()
    return count


def import_bom(file_path):
    wb = openpyxl.load_workbook(file_path)
    ws = wb.active
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM bom")
    count = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        parent_code = str(row[2]).strip() if row[2] else ''  # 父项产品编号
        parent_name = str(row[3]).strip() if row[3] else ''  # 父项产品名称
        child_code = str(row[6]).strip() if row[6] else ''   # 子项产品编号
        child_name = str(row[7]).strip() if row[7] else ''   # 子项产品名称
        
        # Skip if child code starts with "01." (purchased materials)
        if child_code.startswith('01.'):
            continue
            
        qty = abs(float(row[10])) if row[10] else 1  # 单位用量
        unit = str(row[9]).strip() if row[9] else ''  # 子项单位
        process_team = str(row[11]).strip() if row[11] else None  # 备注
        
        c.execute("INSERT INTO bom (parent_product_code, parent_product_name, child_product_code, child_product_name, quantity, unit, process_team) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (parent_code, parent_name, child_code, child_name, qty, unit, process_team))
        count += 1
    conn.commit()
    conn.close()
    return count


def import_process_routes(file_path):
    wb = openpyxl.load_workbook(file_path)
    ws = wb.active
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM process_routes")
    count = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        route_code = str(row[0]).strip()
        route_name = str(row[1]).strip() if row[1] else ''
        process_list = str(row[2]).strip() if row[2] else ''
        if route_code == '工艺路线编号':
            continue
        product_code = route_code.split('-')[0] if '-' in route_code else route_code
        c.execute("INSERT INTO process_routes (route_code, route_name, product_code, process_list) VALUES (?, ?, ?, ?)",
                  (route_code, route_name, product_code, process_list))
        count += 1
    conn.commit()
    conn.close()
    return count


def import_equipment(file_path):
    wb = openpyxl.load_workbook(file_path)
    ws = wb.active
    conn = get_connection()
    c = conn.cursor()
    count = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        equipment_code = str(row[0]).strip()
        equipment_name = str(row[1]).strip() if row[1] else ''
        team_id = int(row[2]) if row[2] else 0
        equipment_type = str(row[3]).strip() if row[3] else 'auto'
        capacity = float(row[4]) if row[4] else 0
        location = str(row[5]).strip() if row[5] else ''
        c.execute("INSERT OR REPLACE INTO equipments (equipment_code, equipment_name, team_id, equipment_type, status, capacity_per_hour, location) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (equipment_code, equipment_name, team_id, equipment_type, 'normal', capacity, location))
        count += 1
    conn.commit()
    conn.close()
    return count


def import_reports(file_path):
    wb = openpyxl.load_workbook(file_path)
    ws = wb.active
    conn = get_connection()
    c = conn.cursor()
    count = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        order_no = str(row[0]).strip() if row[0] else ''
        process_code = str(row[1]).strip() if row[1] else ''
        equipment_id = int(row[2]) if row[2] else None
        team_id = int(row[3]) if row[3] else None
        report_date = row[4].strftime('%Y-%m-%d') if hasattr(row[4], 'strftime') else str(row[4]) if row[4] else ''
        planned_qty = float(row[5]) if row[5] else 0
        actual_qty = float(row[6]) if row[6] else 0
        operator = str(row[7]).strip() if row[7] else ''
        c.execute("INSERT INTO reports (work_order_no, process_code, equipment_id, team_id, report_date, planned_qty, actual_qty, operator) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (order_no, process_code, equipment_id, team_id, report_date, planned_qty, actual_qty, operator))
        count += 1
    conn.commit()
    conn.close()
    return count

def import_equipments(file_path):
    """Import equipments from Excel file. Columns: id, equipment_code, equipment_name, team_name"""
    wb = openpyxl.load_workbook(file_path)
    ws = wb.active
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM equipments")
    c.execute("SELECT id, name FROM teams")
    team_map = {r[1]: r[0] for r in c.fetchall()}
    count = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        eq_code = str(row[1]).strip() if len(row) > 1 and row[1] else ''
        eq_name = str(row[2]).strip() if len(row) > 2 and row[2] else ''
        team_name = str(row[3]).strip() if len(row) > 3 and row[3] else ''
        if not eq_code:
            continue
        team_id = team_map.get(team_name)
        if team_id is None:
            for tn, tid in team_map.items():
                if tn in team_name or team_name in tn:
                    team_id = tid
                    break
        if team_id is None:
            team_id = 1
        c.execute("INSERT INTO equipments (equipment_code, equipment_name, team_id, equipment_type, status, capacity_per_hour, location) VALUES (?,?,?,?,?,?,?)",
                  (eq_code, eq_name, team_id, 'normal', 'normal', 0, ''))
        count += 1
    conn.commit()
    conn.close()
    return count
