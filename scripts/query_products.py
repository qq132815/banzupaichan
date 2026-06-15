# -*- coding: utf-8 -*-
import requests

BASE_URL = "http://localhost:5000"
session = requests.Session()

# 登录
login_data = {"username": "admin", "password": "admin123"}
resp = session.post(f"{BASE_URL}/api/login", json=login_data, timeout=5)

# 查询导入的数据
resp = session.get(f"{BASE_URL}/api/product-definitions?page=1&page_size=10", timeout=10)
data = resp.json()
total = data.get("total", 0)
current = len(data.get("data", []))
print(f"总记录数: {total}")
print(f"当前页记录: {current}")

# 显示前3条数据
if current > 0:
    print("\n前3条数据:")
    for i, item in enumerate(data["data"][:3]):
        product_code = item["product_code"]
        product_name = item["product_name"]
        product_type = item.get("product_type", "")
        customer = item.get("customer", "")
        print(f"{i+1}. {product_code} - {product_name} - {product_type} - {customer}")
