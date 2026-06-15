# -*- coding: utf-8 -*-
import sqlite3
import os
import requests
import time

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "production.db")
IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "images", "products")

def download_sample_images(count=10):
    """下载前N个产品图片作为测试"""
    os.makedirs(IMAGES_DIR, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # 查询前N个有图片URL的产品
    c.execute("SELECT id, product_code, image_url FROM products WHERE image_url IS NOT NULL AND image_url != '' LIMIT ?", (count,))
    products = c.fetchall()
    
    print(f"下载前 {len(products)} 个产品图片")
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
        if '.png' in image_url.lower():
            ext = '.png'
        
        filename = f"{safe_code}{ext}"
        filepath = os.path.join(IMAGES_DIR, filename)
        
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
            print(f"[{i+1}/{len(products)}] 成功 {product_code} - {filename}")
            
            time.sleep(0.5)
            
        except Exception as e:
            fail_count += 1
            print(f"[{i+1}/{len(products)}] 失败 {product_code} - {str(e)}")
    
    conn.commit()
    conn.close()
    
    print("-" * 60)
    print(f"完成: 成功 {success_count}, 失败 {fail_count}")

if __name__ == "__main__":
    download_sample_images(10)
