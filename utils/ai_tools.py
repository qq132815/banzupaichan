# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from utils.db import get_connection


def _today():
    return datetime.now().strftime('%Y-%m-%d')


def _limit(settings):
    try:
        return min(200, max(1, int(settings.get('ai_max_tool_rows') or 50)))
    except Exception:
        return 50


def _ctx_team_id(ctx):
    if (ctx.get('role') or '') == 'team':
        return ctx.get('team_id')
    return None


def _effective_team(ctx, requested_team_id=None):
    forced = _ctx_team_id(ctx)
    if forced:
        return forced
    return requested_team_id


def _rows(cursor):
    return [dict(row) for row in cursor.fetchall()]


def get_work_order_status(ctx, settings, order_no=None, product_code=None, date_from=None, date_to=None):
    conn = get_connection(readonly=True)
    c = conn.cursor()
    params = []
    where = []
    team_id = _ctx_team_id(ctx)
    if team_id:
        where.append('EXISTS (SELECT 1 FROM schedules s WHERE s.work_order_no=work_orders.order_no AND s.team_id=?)')
        params.append(team_id)
    if order_no:
        where.append('order_no LIKE ?')
        params.append('%' + order_no + '%')
    if product_code:
        where.append('product_code LIKE ?')
        params.append('%' + product_code + '%')
    if date_from:
        where.append('due_date >= ?')
        params.append(date_from)
    if date_to:
        where.append('due_date <= ?')
        params.append(date_to)
    sql = '''SELECT order_no, product_code, product_name, quantity, completed_qty,
                    due_date, priority, status, process_progress, create_time
             FROM work_orders'''
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY due_date IS NULL, due_date, priority DESC LIMIT ?'
    params.append(_limit(settings))
    c.execute(sql, params)
    data = _rows(c)
    conn.close()
    return {'name': 'get_work_order_status', 'data': data}


def get_schedule_summary(ctx, settings, date=None, team_id=None, equipment_id=None):
    date = date or _today()
    team_id = _effective_team(ctx, team_id)
    conn = get_connection(readonly=True)
    c = conn.cursor()
    params = [date]
    where = ['s.schedule_date=?']
    if team_id:
        where.append('s.team_id=?')
        params.append(team_id)
    if equipment_id:
        where.append('s.equipment_id=?')
        params.append(equipment_id)
    sql = '''SELECT s.schedule_date, t.name AS team_name, e.equipment_code, e.equipment_name,
                    s.work_order_no, s.product_code, s.process_name, s.quantity,
                    s.hours, s.start_time, s.end_time, s.task_status, s.is_overtime
             FROM schedules s
             LEFT JOIN teams t ON s.team_id=t.id
             LEFT JOIN equipments e ON s.equipment_id=e.id
             WHERE ''' + ' AND '.join(where) + '''
             ORDER BY t.name, e.equipment_code, s.start_time LIMIT ?'''
    params.append(_limit(settings))
    c.execute(sql, params)
    data = _rows(c)
    conn.close()
    return {'name': 'get_schedule_summary', 'data': data}


def get_equipment_load(ctx, settings, date=None, team_id=None, equipment_code=None):
    date = date or _today()
    team_id = _effective_team(ctx, team_id)
    conn = get_connection(readonly=True)
    c = conn.cursor()
    params = [date]
    where = ['s.schedule_date=?']
    if team_id:
        where.append('s.team_id=?')
        params.append(team_id)
    if equipment_code:
        where.append('e.equipment_code LIKE ?')
        params.append('%' + equipment_code + '%')
    sql = '''SELECT t.name AS team_name, e.equipment_code, e.equipment_name,
                    COUNT(s.id) AS task_count,
                    ROUND(COALESCE(SUM(s.hours),0), 2) AS planned_hours,
                    ROUND(COALESCE(SUM(s.quantity),0), 2) AS planned_qty
             FROM schedules s
             LEFT JOIN teams t ON s.team_id=t.id
             LEFT JOIN equipments e ON s.equipment_id=e.id
             WHERE ''' + ' AND '.join(where) + '''
             GROUP BY s.team_id, s.equipment_id
             ORDER BY planned_hours DESC LIMIT ?'''
    params.append(_limit(settings))
    c.execute(sql, params)
    data = _rows(c)
    conn.close()
    return {'name': 'get_equipment_load', 'data': data}


def get_active_alerts(ctx, settings, level=None, team_id=None):
    # Existing alerts are product/order based and may not contain team_id, so team users get non-global rows only when linked through schedules.
    team_id = _effective_team(ctx, team_id)
    conn = get_connection(readonly=True)
    c = conn.cursor()
    params = []
    where = ["COALESCE(a.status,'') NOT IN ('closed','done')"]
    if level:
        where.append('a.alert_level=?')
        params.append(level)
    if team_id:
        where.append('EXISTS (SELECT 1 FROM schedules s WHERE s.work_order_no=a.order_no AND s.team_id=?)')
        params.append(team_id)
    sql = '''SELECT a.product_code, a.order_no, a.alert_level, a.due_date, a.quantity,
                    a.scheduled_qty, a.shortage_qty, a.days_remaining, a.message, a.status
             FROM alerts a
             WHERE ''' + ' AND '.join(where) + '''
             ORDER BY CASE a.alert_level WHEN 'red' THEN 1 WHEN 'yellow' THEN 2 ELSE 3 END,
                      a.due_date LIMIT ?'''
    params.append(_limit(settings))
    c.execute(sql, params)
    data = _rows(c)
    conn.close()
    return {'name': 'get_active_alerts', 'data': data}


def get_material_alerts(ctx, settings, status=None, team_id=None):
    team_id = _effective_team(ctx, team_id)
    conn = get_connection(readonly=True)
    c = conn.cursor()
    params = []
    where = []
    if status:
        where.append('ma.status=?')
        params.append(status)
    if team_id:
        where.append('EXISTS (SELECT 1 FROM schedules s WHERE s.work_order_no=ma.parent_order_no AND s.team_id=?)')
        params.append(team_id)
    sql = '''SELECT ma.child_order_no, ma.child_product_code, ma.child_product_name,
                    ma.parent_order_no, ma.parent_product_code, ma.parent_product_name,
                    ma.trigger_process, ma.trigger_qty, ma.trigger_time, ma.status, ma.created_at
             FROM material_alerts ma'''
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY ma.created_at DESC LIMIT ?'
    params.append(_limit(settings))
    c.execute(sql, params)
    data = _rows(c)
    conn.close()
    return {'name': 'get_material_alerts', 'data': data}


def get_work_report_summary(ctx, settings, date_from=None, date_to=None, team_id=None):
    date_to = date_to or _today()
    date_from = date_from or date_to
    team_id = _effective_team(ctx, team_id)
    conn = get_connection(readonly=True)
    c = conn.cursor()
    params = [date_from + ' 00:00:00', date_to + ' 23:59:59']
    where = ['wr.start_time BETWEEN ? AND ?']
    if team_id:
        where.append('EXISTS (SELECT 1 FROM schedules s WHERE s.work_order_no=wr.order_no AND s.team_id=?)')
        params.append(team_id)
    sql = '''SELECT wr.process_name, wr.product_code, wr.product_name,
                    COUNT(*) AS report_count,
                    ROUND(COALESCE(SUM(wr.report_qty),0), 2) AS report_qty,
                    ROUND(COALESCE(SUM(wr.good_qty),0), 2) AS good_qty,
                    ROUND(COALESCE(SUM(wr.report_hours),0), 2) AS report_hours
             FROM work_reports wr
             WHERE ''' + ' AND '.join(where) + '''
             GROUP BY wr.process_name, wr.product_code, wr.product_name
             ORDER BY report_qty DESC LIMIT ?'''
    params.append(_limit(settings))
    c.execute(sql, params)
    data = _rows(c)
    conn.close()
    return {'name': 'get_work_report_summary', 'data': data}


def get_shipping_plan(ctx, settings, date_from=None, date_to=None, product_code=None):
    conn = get_connection(readonly=True)
    c = conn.cursor()
    params = []
    where = []
    team_id = _ctx_team_id(ctx)
    if team_id:
        where.append('''EXISTS (
            SELECT 1 FROM production_requirements pr
            JOIN teams t ON pr.team_name=t.name
            WHERE pr.product_code=shipping_plan.product_code AND t.id=?
        )''')
        params.append(team_id)
    if date_from:
        where.append('ship_date >= ?')
        params.append(date_from)
    if date_to:
        where.append('ship_date <= ?')
        params.append(date_to)
    if product_code:
        where.append('product_code LIKE ?')
        params.append('%' + product_code + '%')
    sql = '''SELECT product_code, product_name, quantity, ship_date, customer, project, k3_order_no
             FROM shipping_plan'''
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY ship_date LIMIT ?'
    params.append(_limit(settings))
    c.execute(sql, params)
    data = _rows(c)
    conn.close()
    return {'name': 'get_shipping_plan', 'data': data}


def get_production_requirements(ctx, settings, date_from=None, date_to=None, team_id=None):
    team_id = _effective_team(ctx, team_id)
    conn = get_connection(readonly=True)
    c = conn.cursor()
    params = []
    where = []
    if date_from:
        where.append('pr.required_date >= ?')
        params.append(date_from)
    if date_to:
        where.append('pr.required_date <= ?')
        params.append(date_to)
    join_team = ''
    if team_id:
        join_team = ' LEFT JOIN teams t ON pr.team_name=t.name '
        where.append('t.id=?')
        params.append(team_id)
    sql = '''SELECT pr.product_code, pr.product_name, pr.ship_date, pr.ship_quantity,
                    pr.required_date, pr.required_quantity, pr.team_name, pr.process_name, pr.status
             FROM production_requirements pr''' + join_team
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY pr.required_date LIMIT ?'
    params.append(_limit(settings))
    c.execute(sql, params)
    data = _rows(c)
    conn.close()
    return {'name': 'get_production_requirements', 'data': data}


def _extract_date(question):
    q = question or ''
    if '明天' in q:
        return (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    if '昨天' in q:
        return (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    m = __import__('re').search(r'(20\d{2}-\d{1,2}-\d{1,2})', q)
    if m:
        parts = m.group(1).split('-')
        return '%04d-%02d-%02d' % (int(parts[0]), int(parts[1]), int(parts[2]))
    return _today()


def _extract_order_no(question):
    import re
    q = question or ''
    m = re.search(r'(?:工单|订单)\s*[:：#]?\s*([A-Za-z0-9_\-]+)', q)
    return m.group(1) if m else None


def _extract_equipment_code(question):
    import re
    q = question or ''
    m = re.search(r'([A-Za-z]{1,4}\d+[A-Za-z0-9\-]*)', q)
    return m.group(1) if m else None


def run_relevant_tools(question, ctx, settings):
    q = question or ''
    date = _extract_date(q)
    results = []
    if any(k in q for k in ['排班', '排产', '任务', '今天排', '明天排']):
        results.append(get_schedule_summary(ctx, settings, date=date, equipment_id=None))
    if any(k in q for k in ['设备', '负荷', '产能', 'WG', '机台']):
        results.append(get_equipment_load(ctx, settings, date=date, equipment_code=_extract_equipment_code(q)))
    if any(k in q for k in ['预警', '延期', '风险', '告警']):
        results.append(get_active_alerts(ctx, settings))
    if any(k in q for k in ['备料', '物料', '缺料']):
        results.append(get_material_alerts(ctx, settings, status=None))
    if any(k in q for k in ['报工', '完成', '效率', '产量']):
        results.append(get_work_report_summary(ctx, settings, date_from=date, date_to=date))
    if any(k in q for k in ['发货', '交付', '交期']):
        results.append(get_shipping_plan(ctx, settings, date_from=date, date_to=None))
    if any(k in q for k in ['需求', '生产需求', '半成品']):
        results.append(get_production_requirements(ctx, settings, date_from=date, date_to=None))
    order_no = _extract_order_no(q)
    if order_no or any(k in q for k in ['工单', '订单', '进度', '状态']):
        results.append(get_work_order_status(ctx, settings, order_no=order_no))
    if not results:
        results.append(get_active_alerts(ctx, settings))
        results.append(get_schedule_summary(ctx, settings, date=date))
    return results
