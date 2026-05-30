# -*- coding: utf-8 -*-
"""DingTalk API integration for attendance data."""
import requests
import time
from datetime import datetime, timedelta

# Configuration - should be stored in system_settings table
DINGTALK_CONFIG = {
    'app_key': '',
    'app_secret': '',
    'base_url': 'https://oapi.dingtalk.com',
}

def get_access_token():
    """Get DingTalk access token."""
    config = get_config()
    if not config.get('app_key') or not config.get('app_secret'):
        return None
    url = f"{DINGTALK_CONFIG['base_url']}/gettoken"
    resp = requests.get(url, params={
        'appkey': config['app_key'],
        'appsecret': config['app_secret']
    }, timeout=10)
    data = resp.json()
    return data.get('access_token')

def get_config():
    """Get DingTalk config from database."""
    from utils.db import get_connection
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT key, value FROM system_settings WHERE key LIKE 'dingtalk_%'")
    config = {row[0].replace('dingtalk_', ''): row[1] for row in c.fetchall()}
    conn.close()
    return config

def fetch_attendance(date_from, date_to, user_ids=None):
    """Fetch attendance data from DingTalk API.
    Returns list of dicts with: user_id, name, work_date, check_in, check_out,
    work_hours, is_overtime, leave_type
    """
    token = get_access_token()
    if not token:
        return []
    
    url = f"{DINGTALK_CONFIG['base_url']}/topapi/attendance/v2/list"
    results = []
    
    # DingTalk API has pagination, iterate
    offset = 0
    limit = 50
    while True:
        payload = {
            'workDateFrom': f"{date_from} 00:00:00",
            'workDateTo': f"{date_to} 23:59:59",
            'offset': offset,
            'limit': limit,
        }
        if user_ids:
            payload['userIdList'] = user_ids
        
        headers = {'x-acs-dingtalk-access-token': token}
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        data = resp.json()
        
        records = data.get('result', {}).get('record', [])
        if not records:
            break
        
        for rec in records:
            # Parse check times
            check_in = ''
            check_out = ''
            if rec.get('userCheckTime'):
                check_in = rec['userCheckTime']
            
            work_duration = rec.get('workDuration', 0) / 3600  # seconds to hours
            
            # Overtime detection
            plan_duration = rec.get('planDuration', 0) / 3600
            is_overtime = 1 if work_duration > plan_duration and plan_duration > 0 else 0
            
            # Leave type
            leave_type = ''
            if rec.get('leaveStatus') == 'APPROVED':
                leave_type = rec.get('leaveType', '')
            
            results.append({
                'user_id': rec.get('userId', ''),
                'name': rec.get('userName', ''),
                'work_date': rec.get('workDate', '')[:10],
                'check_in': check_in,
                'check_out': check_out,
                'work_hours': round(work_duration, 2),
                'plan_hours': round(plan_duration, 2),
                'is_overtime': is_overtime,
                'leave_type': leave_type,
            })
        
        offset += limit
        if len(records) < limit:
            break
    
    return results


def sync_attendance(date_from, date_to):
    """Sync attendance data from DingTalk to local database."""
    from utils.db import get_connection
    records = fetch_attendance(date_from, date_to)
    if not records:
        return 0
    
    conn = get_connection()
    c = conn.cursor()
    count = 0
    for rec in records:
        c.execute("""INSERT OR REPLACE INTO attendance 
            (user_id, name, work_date, check_in, check_out, work_hours, plan_hours, is_overtime, leave_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rec['user_id'], rec['name'], rec['work_date'], rec['check_in'],
             rec['check_out'], rec['work_hours'], rec['plan_hours'],
             rec['is_overtime'], rec['leave_type']))
        count += 1
    conn.commit()
    conn.close()
    return count
