# -*- coding: utf-8 -*-
import requests

BASE_URL = "http://localhost:5000"
session = requests.Session()

# 登录
login_data = {"username": "admin", "password": "admin123"}
resp = session.post(f"{BASE_URL}/api/login", json=login_data, timeout=5)

# 获取页面内容
resp = session.get(f"{BASE_URL}/products/definitions", timeout=10)
content = resp.text

# 检查JavaScript函数是否存在
functions = [
    "function startImageDownload",
    "function showDownloadProgressModal", 
    "function startProgressPolling",
    "function updateProgressDisplay",
    "function closeDownloadProgressModal"
]

for func in functions:
    if func in content:
        print(f"[OK] {func} 存在")
    else:
        print(f"[FAIL] {func} 不存在")
