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
        
        # Calculate work hours and insert
        for key, p in persons.items():
            work_hours = 0
            is_overtime = 0
            leave_type = ''
            
            if p['check_in'] and p['check_out']:
                try:
                    t_in = datetime.strptime(p['check_in'], '%Y-%m-%d %H:%M:%S')
                    t_out = datetime.strptime(p['check_out'], '%Y-%m-%d %H:%M:%S')
                    delta = (t_out - t_in).total_seconds() / 3600
                    # Subtract lunch break (1 hour) if work span covers noon
                    if t_in.hour < 12 and t_out.hour >= 13:
                        delta -= 1.0
                    work_hours = round(max(0, delta), 2)
                    # Overtime: if work > 8 hours
                    if work_hours > 8:
                        is_overtime = 1
                except:
                    pass
            
            # Handle leave: if timeResult contains leave info
            if 'Leave' in (p['time_result_in'] + p['time_result_out']):
                leave_type = '请假'
            
            # Calculate plan_hours (standard 8h for full day)
            plan_hours = 8.0
            
            c.execute("""INSERT OR REPLACE INTO attendance 
                (user_id, name, work_date, check_in, check_out, work_hours, plan_hours, is_overtime, leave_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (p['user_id'], p['name'], p['work_date'], p['check_in'],
                 p['check_out'], work_hours, plan_hours, is_overtime, leave_type))
            total_count += 1
        
        current += timedelta(days=1)
    
    # Auto-add new attendance names to personnel table
    c.execute("""INSERT OR IGNORE INTO personnel (name, department, position, is_active)
        SELECT DISTINCT a.name, '', '', 1 FROM attendance a
        WHERE a.name != '' AND a.name NOT IN (SELECT name FROM personnel)""")
    new_count = c.rowcount
    conn.commit()
    conn.close()
    if new_count > 0:
        print(f"[attendance] Added {new_count} new names to personnel")
    return total_count