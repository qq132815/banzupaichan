# -*- coding: utf-8 -*-
import sqlite3
import os
import requests
import time
import sys

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "production.db")
IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "images", "products")

def download_images_batch(start=0, count=100):
    """批量下载产品图片
    
    Args:
        start: 起始索引
        count: 下载数量
    """
    os.makedirs(IMAGES_DIR, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # 查询有图片URL的产品
    c.execute("SELECT id, product_code, image_url FROM products WHERE image_url IS NOT NULL AND image_url != '' LIMIT ? OFFSET ?", (count, start))
    products = c.fetchall()
    
    total = len(products)
    print(f"下载 {start+1} 到 {start+total} 的产品图片")
    print(f"图片保存目录: {IMAGES_DIR}")
    print("-" * 60)
    
    success_count = 0
    fail_count = 0
    
    for i, product in enumerate(products):
        product_id = product['id']
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
        
        # 如果文件已存在，跳过
        if os.path.exists(filepath):
            print(f"[{i+1}/{total}] 跳过 {product_code} - 文件已存在")
            continue
        
        # 下载图片
        try:
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            # 更新数据库
            image_path = f"/static/images/products/{filename}"
            c.execute("UPDATE products SET image_path=? WHERE id=?", (image_path, product_id))
            
            success_count += 1
            print(f"[{i+1}/{total}] 成功 {product_code} - {filename}")
            
            # 避免请求过快
            time.sleep(0.2)
            
        except Exception as e:
            fail_count += 1
            print(f"[{i+1}/{total}] 失败 {product_code} - {str(e)}")
        
        # 每50个提交一次
        if (i + 1) % 50 == 0:
            conn.commit()
    
    conn.commit()
    conn.close()
    
    print("-" * 60)
    print(f"完成: 成功 {success_count}, 失败 {fail_count}")

if __name__ == "__main__":
    # 命令行参数
    if len(sys.argv) > 1:
        start = int(sys.argv[1])
    else:
        start = 0
    
    if len(sys.argv) > 2:
        count = int(sys.argv[2])
    else:
        count = 100
    
    download_images_batch(start, count)
