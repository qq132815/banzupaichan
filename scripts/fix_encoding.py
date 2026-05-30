#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE, 'data', 'production.db')

def get_connection():
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def rebuild_database():
    print('Rebuilding database...')
    conn = get_connection()
    c = conn.cursor()
    
    # Drop all tables
    for t in ['alerts','bom','production_cycles','shipping_plan','reports','schedules','process_equipment','processes','process_routes','work_orders','products','equipments','teams']:
        c.execute('DROP TABLE IF EXISTS ' + t)
    
    # Create teams
    c.execute('CREATE TABLE teams (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, leader TEXT, members TEXT, shift_type TEXT, shift_start TEXT, shift_end TEXT)')
    
    # Create equipments
    c.execute('CREATE TABLE equipments (id INTEGER PRIMARY KEY AUTOINCREMENT, equipment_code TEXT NOT NULL UNIQUE, equipment_name TEXT NOT NULL, team_id INTEGER, equipment_type TEXT, status TEXT, capacity_per_hour REAL, location TEXT)')
    
    # Create products
    c.execute('CREATE TABLE products (id INTEGER PRIMARY KEY AUTOINCREMENT, product_code TEXT NOT NULL UNIQUE, product_name TEXT, product_type TEXT, safety_stock REAL, unit TEXT)')
    
    # Create work_orders
    c.execute('CREATE TABLE work_orders (id INTEGER PRIMARY KEY AUTOINCREMENT, order_no TEXT, product_code TEXT, product_name TEXT, quantity REAL, completed_qty REAL, due_date TEXT, priority TEXT, status TEXT, source TEXT, parent_order_no TEXT)')
    
    # Create process_routes
    c.execute('CREATE TABLE process_routes (id INTEGER PRIMARY KEY AUTOINCREMENT, route_code TEXT, route_name TEXT, product_code TEXT, process_list TEXT, remark TEXT)')
    
    # Create processes
    c.execute('CREATE TABLE processes (id INTEGER PRIMARY KEY AUTOINCREMENT, process_code TEXT NOT NULL UNIQUE, process_name TEXT, team_name TEXT)')
    
    # Create process_equipment
    c.execute('CREATE TABLE process_equipment (id INTEGER PRIMARY KEY AUTOINCREMENT, process_code TEXT NOT NULL, equipment_id INTEGER NOT NULL, is_primary INTEGER, setup_time INTEGER)')
    
    # Create schedules
    c.execute('CREATE TABLE schedules (id INTEGER PRIMARY KEY AUTOINCREMENT, equipment_id INTEGER, work_order_no TEXT, process_code TEXT, process_name TEXT, schedule_date TEXT, start_time TEXT, end_time TEXT, quantity REAL, hours REAL, capacity_per_hour REAL, is_overtime INTEGER, team_id INTEGER, task_status TEXT, priority TEXT, operator TEXT)')
    
    # Create reports
    c.execute('CREATE TABLE reports (id INTEGER PRIMARY KEY AUTOINCREMENT, work_order_no TEXT, process_code TEXT, equipment_id INTEGER, team_id INTEGER, report_date TEXT, planned_qty REAL, actual_qty REAL, operator TEXT)')
    
    # Create shipping_plan
    c.execute('CREATE TABLE shipping_plan (id INTEGER PRIMARY KEY AUTOINCREMENT, product_code TEXT NOT NULL, quantity REAL, ship_date TEXT, k3_order_no TEXT)')
    
    # Create production_cycles
    c.execute('CREATE TABLE production_cycles (id INTEGER PRIMARY KEY AUTOINCREMENT, product_code TEXT NOT NULL, production_days REAL, lead_days REAL)')
    
    # Create bom
    c.execute('CREATE TABLE bom (id INTEGER PRIMARY KEY AUTOINCREMENT, parent_product_code TEXT, parent_product_name TEXT, child_product_code TEXT, child_product_name TEXT, quantity REAL, unit TEXT, process_team TEXT)')
    
    # Create alerts
    c.execute('CREATE TABLE alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, product_code TEXT, order_no TEXT, alert_level TEXT, due_date TEXT, quantity REAL, scheduled_qty REAL, shortage_qty REAL, days_remaining INTEGER, message TEXT, status TEXT)')
    
    # Create indexes
    c.execute('CREATE INDEX IF NOT EXISTS idx_sp_date ON shipping_plan(ship_date)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_alert_lvl ON alerts(alert_level)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_schedule_date ON schedules(schedule_date)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_schedule_team ON schedules(team_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_wo_product ON work_orders(product_code)')
    
    conn.commit()
    print('Tables created successfully')
    return conn

if __name__ == '__main__':
    rebuild_database()
    print('Database rebuilt successfully!')
