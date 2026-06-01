# -*- coding: utf-8 -*-
"""Attendance API integration - replaces DingTalk with custom attendance system."""
import requests
from datetime import datetime, timedelta


def get_attendance_config():
    """Get attendance API config from database."""
    from utils.db import get_connection
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT key, value FROM system_settings WHERE key LIKE 'attendance_%'")
    config = {row[0].replace('attendance_', ''): row[1] for row in c.fetchall()}
    conn.close()
    return {
        'api_url': config.get('api_url') or 'http://10.6.201.10:7777/ddkq/api/third-party/attendance',
        'api_key': config.get('api_key') or 'tk_cs_20260601',
    }


def fetch_attendance(date_str):
    """Fetch attendance data for a single date from the API.
    
    Args:
        date_str: Date in YYYY-MM-DD format
    
    Returns:
        list of dicts with: userid, employeeName, deptName, workDate,
        userCheckTime, baseCheckTime, timeResult, checkType
    """
    config = get_attendance_config()
    if not config.get('api_url') or not config.get('api_key'):
        return []
    
    headers = {
        'X-API-Key': config['api_key'],
        'Accept': 'application/json',
    }
    
    try:
        resp = requests.get(
            config['api_url'],
            params={'date': date_str},
            headers=headers,
            timeout=30,
        )
        data = resp.json()
        if data.get('success'):
            return data.get('data', {}).get('records', [])
        else:
            print(f"[attendance_api] API error: {data.get('message', 'unknown')}")
            return []
    except Exception as e:
        print(f"[attendance_api] Request error: {e}")
        return []


def sync_attendance(date_from, date_to):
    """Sync attendance data from API to local database.
    
    For each date in range, fetch records and merge check-in/check-out
    into single attendance rows per person per day.
    
    Returns count of records synced.
    """
    from utils.db import get_connection
    from datetime import datetime, timedelta
    
    start = datetime.strptime(date_from, '%Y-%m-%d')
    end = datetime.strptime(date_to, '%Y-%m-%d')
    
    conn = get_connection()
    c = conn.cursor()
    total_count = 0
    
    current = start
    while current <= end:
        date_str = current.strftime('%Y-%m-%d')
        records = fetch_attendance(date_str)
        
        # Group by userid: merge OnDuty and OffDuty into one row
        persons = {}
        for rec in records:
            uid = rec.get('userid', '')
            name = rec.get('employeeName', '')
            check_time = rec.get('userCheckTime', '')
            check_type = rec.get('checkType', '')  # OnDuty or OffDuty
            time_result = rec.get('timeResult', '')  # Normal, Late, Early, etc.
            dept = rec.get('deptName', '')
            
            key = uid or name
            if key not in persons:
                persons[key] = {
                    'user_id': uid,
                    'name': name,
                    'work_date': date_str,
                    'check_in': '',
                    'check_out': '',
                    'dept': dept,
                    'time_result_in': '',
                    'time_result_out': '',
                }
            
            if check_type == 'OnDuty':
                persons[key]['check_in'] = check_time
                persons[key]['time_result_in'] = time_result
            elif check_type == 'OffDuty':
                persons[key]['check_out'] = check_time
                persons[key]['time_result_out'] = time_result
        
        # Calculate work hours with shift rules:
        # Morning: 08:00-11:45 (3.75h), Afternoon: 12:45-17:00 (4.25h)
        # Normal total: 8h. Overtime: after 17:30, 30min units, <30min ignored
        for key, p in persons.items():
            normal_hours = 0.0
            overtime_hours = 0.0
            work_hours = 0.0
            is_overtime = 0
            leave_type = ''
            
            if p['check_in'] and p['check_out']:
                try:
                    t_in = datetime.strptime(p['check_in'], '%Y-%m-%d %H:%M:%S')
                    t_out = datetime.strptime(p['check_out'], '%Y-%m-%d %H:%M:%S')
                    
                    # Morning: 08:00 ~ 11:45
                    m_s = max(t_in, t_in.replace(hour=8, minute=0, second=0))
                    m_e = min(t_out, t_in.replace(hour=11, minute=45, second=0))
                    if m_e > m_s and t_in < t_in.replace(hour=11, minute=45, second=0) and t_out > t_in.replace(hour=8, minute=0, second=0):
                        normal_hours += (m_e - m_s).total_seconds() / 3600
                    
                    # Afternoon: 12:45 ~ 17:00
                    a_s = max(t_in, t_in.replace(hour=12, minute=45, second=0))
                    a_e = min(t_out, t_in.replace(hour=17, minute=0, second=0))
                    if a_e > a_s and t_in < t_in.replace(hour=17, minute=0, second=0) and t_out > t_in.replace(hour=12, minute=45, second=0):
                        normal_hours += (a_e - a_s).total_seconds() / 3600
                    
                    normal_hours = round(min(normal_hours, 8.0), 2)
                    
                    # Overtime: after 17:30
                    ot_start = t_in.replace(hour=17, minute=30, second=0)
                    if t_out > ot_start:
                        ot_begin = max(t_in, ot_start)
                        ot_raw = (t_out - ot_begin).total_seconds() / 3600
                        overtime_hours = int(ot_raw * 2) / 2.0  # floor to 0.5h
                        is_overtime = 1 if overtime_hours > 0 else 0
                    
                    work_hours = round(normal_hours + overtime_hours, 2)
                except:
                    pass
            
            if 'Leave' in (p['time_result_in'] + p['time_result_out']):
                leave_type = '请假'
            
            plan_hours = 8.0
            
            # Only insert if user_id matches a production worker in personnel
            c.execute("""INSERT OR REPLACE INTO attendance 
                (user_id, name, work_date, check_in, check_out, work_hours, plan_hours, is_overtime, leave_type, normal_hours, overtime_hours)
                SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ? WHERE EXISTS (
                    SELECT 1 FROM personnel WHERE user_id = ?
                )""",
                (p['user_id'], p['name'], p['work_date'], p['check_in'],
                 p['check_out'], work_hours, plan_hours, is_overtime, leave_type, normal_hours, overtime_hours, p['user_id']))
            total_count += c.rowcount
        
        current += timedelta(days=1)
    
    conn.commit()
    conn.close()
    return total_count