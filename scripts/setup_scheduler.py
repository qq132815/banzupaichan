# -*- coding: utf-8 -*-
"""Setup Windows Task Scheduler for hourly MES data fetch."""
import subprocess, os, sys

TASK_NAME = "MES_AutoFetch_Reports"
SCRIPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'auto_fetch_reports.py')
PYTHON_PATH = sys.executable
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'downloads', 'fetch_log.txt')

# Delete existing task if any
subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], capture_output=True)

# Create scheduled task: runs every hour from 8:00 to 20:00
cmd = [
    "schtasks", "/Create",
    "/TN", TASK_NAME,
    "/TR", '"%s" "%s" >> "%s" 2>&1' % (PYTHON_PATH, SCRIPT_PATH, LOG_PATH),
    "/SC", "DAILY",
    "/ST", "08:00",
    "/RI", "60",  # repeat every 60 minutes
    "/DU", "13:00",  # for 13 hours (8:00-21:00)
    "/F"  # force overwrite
]
result = subprocess.run(cmd, capture_output=True, text=True)
if result.returncode == 0:
    print("Task '%s' created successfully!" % TASK_NAME)
    print("Schedule: Every hour from 08:00 to 21:00 daily")
else:
    print("Error: %s" % result.stderr)
