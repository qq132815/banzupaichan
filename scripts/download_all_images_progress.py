# -*- coding: utf-8 -*-
import sqlite3
import os
import requests
import time
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "production.db")
IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "images", "products")

def get_progress_file():
    """获取进度文件路径"""
    return os.environ.get('PROGRESS_FILE', 
                         os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'download_progress.json'))

def update_progress(progress_file, **kwargs):
    """更新进度文件"""
    try:
        if os.path.exists(progress_file):
            with open(progress_file, 'r', encoding='utf-8') as f:
                progress = json.load(f)
        else:
            progress = {}
        
        progress.update(kwargs)
        
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump(progress, f, ensure_ascii=False)
    except Exception as e:
        print(f"更新进度文件失败: {e}")

def download_all_product_images(batch_size=50, delay=0.05):
    """批量下载所有产品图片（带进度报告）"""
    progress_file = get_progress_file()
    os.makedirs(IMAGES_DIR, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # 查询所有有图片URL的产品
    c.execute("SELECT id, product_code, image_url FROM products WHERE image_url IS NOT NULL AND image_url != ''")
    products = c.fetchall()
    
    total = len(products)
    
    # 更新进度：总数
    update_progress(progress_file, 
                   total=total, 
                   current=0, 
                   success=0, 
                   fail=0, 
                   skip=0,
                   message=f"开始下载 {total} 个产品图片...")
    
    print(f"共有 {total} 个产品需要下载图片")
    print(f"图片保存目录: {IMAGES_DIR}")
    print(f"进度文件: {progress_file}")
    print("-" * 60)
    
    success_count = 0
    fail_count = 0
    skip_count = 0
    
    for i, product in enumerate(products):
        product_id = product['id']
        product_code = product['product_code']
        image_url = product['image_url']
        
        if not image_url:
            continue
        
        # 生成文件名（使用产品编码，替换特殊字符）
        safe_code = product_code.replace('/', '_').replace('\\', '_').replace(':', '_').replace('.', '_')
        
        # 根据URL判断扩展名
        ext = '.jpg'
        url_lower = image_url.lower()
        if '.png' in url_lower:
            ext = '.png'
        elif '.gif' in url_lower:
            ext = '.gif'
        elif '.jpeg' in url_lower:
            ext = '.jpeg'
        elif '.webp' in url_lower:
            ext = '.webp'
        
        filename = f"{safe_code}{ext}"
        filepath = os.path.join(IMAGES_DIR, filename)
        
        # 如果文件已存在，跳过
        if os.path.exists(filepath):
            skip_count += 1
            
            # 更新数据库中的image_path（如果为空）
            image_path = f"/static/images/products/{filename}"
            c.execute("UPDATE products SET image_path=? WHERE id=? AND (image_path IS NULL OR image_path='')", 
                     (image_path, product_id))
            
            # 更新进度
            update_progress(progress_file,
                           current=i+1,
                           skip=skip_count,
                           message=f"[{i+1}/{total}] 跳过 {product_code} - 文件已存在")
            
            if skip_count % 100 == 0:
                print(f"[{i+1}/{total}] 跳过 {product_code} - 文件已存在 (已跳过 {skip_count} 个)")
            continue
        
        # 下载图片
        try:
            response = requests.get(image_url, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            # 更新数据库中的image_path
            image_path = f"/static/images/products/{filename}"
            c.execute("UPDATE products SET image_path=? WHERE id=?", (image_path, product_id))
            
            success_count += 1
            
            # 更新进度
            update_progress(progress_file,
                           current=i+1,
                           success=success_count,
                           message=f"[{i+1}/{total}] 成功 {product_code} - {filename}")
            
            print(f"[{i+1}/{total}] 成功 {product_code} - {filename} ({len(response.content)} 字节)")
            
            # 避免请求过快
            time.sleep(delay)
            
        except Exception as e:
            fail_count += 1
            
            # 更新进度
            update_progress(progress_file,
                           current=i+1,
                           fail=fail_count,
                           message=f"[{i+1}/{total}] 失败 {product_code} - {str(e)}")
            
            print(f"[{i+1}/{total}] 失败 {product_code} - {str(e)}")
        
        # 每批提交一次数据库
        if (i + 1) % batch_size == 0:
            conn.commit()
            print(f"--- 已处理 {i+1}/{total} ---")
    
    conn.commit()
    conn.close()
    
    # 最终更新进度
    update_progress(progress_file,
                   current=total,
                   success=success_count,
                   fail=fail_count,
                   skip=skip_count,
                   message=f"下载完成: 成功{success_count}个, 失败{fail_count}个, 跳过{skip_count}个")
    
    print("-" * 60)
    print(f"下载完成: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"成功: {success_count}")
    print(f"失败: {fail_count}")
    print(f"跳过: {skip_count}")
    print(f"总计: {success_count + fail_count + skip_count}")

if __name__ == "__main__":
    # 可以调整参数
    # batch_size: 每批处理数量
    # delay: 每次请求间隔（秒），避免请求过快
    download_all_product_images(batch_size=50, delay=0.1)


