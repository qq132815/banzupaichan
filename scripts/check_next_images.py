# -*- coding: utf-8 -*-
import sqlite3
import os
import requests
import time

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "production.db")
IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "images", "products")

def check_next_images(count=10):
    """检查接下来要下载的图片"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # 查询所有有图片URL的产品
    c.execute("SELECT id, product_code, image_url FROM products WHERE image_url IS NOT NULL AND image_url != ''")
    products = c.fetchall()
    
    print(f"总产品数: {len(products)}")
    
    # 找到第一个未下载的图片
    for i, product in enumerate(products):
        product_code = product['product_code']
        image_url = product['image_url']
        
        # 生成文件名
        safe_code = product_code.replace('/', '_').replace('\\', '_').replace(':', '_').replace('.', '_')
        ext = '.jpg'
        url_lower = image_url.lower()
        if '.png' in url_lower:
            ext = '.png'
        elif '.gif' in url_lower:
            ext = '.gif'
        elif '.jpeg' in url_lower:
            ext = '.jpeg'
        
        filename = f"{safe_code}{ext}"
        filepath = os.path.join(IMAGES_DIR, filename)
        
        if not os.path.exists(filepath):
            print(f"[{i+1}] 未下载: {product_code}")
            print(f"    URL: {image_url}")
            print(f"    文件: {filename}")
            
            # 测试下载
            try:
                start_time = time.time()
                response = requests.get(image_url, timeout=10)
                elapsed = time.time() - start_time
                print(f"    状态: {response.status_code}")
                print(f"    大小: {len(response.content)} 字节")
                print(f"    耗时: {elapsed:.2f} 秒")
            except Exception as e:
                print(f"    错误: {e}")
            
            count -= 1
            if count <= 0:
                break
    
    conn.close()

if __name__ == "__main__":
    check_next_images(5)
