# -*- coding: utf-8 -*-
import json
import os
import time
from datetime import datetime

PROGRESS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "download_progress.json")

def simulate_download_progress():
    """模拟下载进度"""
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    
    # 初始化进度
    progress = {
        'status': 'running',
        'total': 100,
        'current': 0,
        'success': 0,
        'fail': 0,
        'skip': 0,
        'message': '开始模拟下载...',
        'start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False)
    
    print(f"进度文件: {PROGRESS_FILE}")
    print("开始模拟下载进度...")
    print("-" * 60)
    
    for i in range(101):
        time.sleep(0.05)
        
        # 更新进度
        progress['current'] = i
        progress['success'] = int(i * 0.9)
        progress['fail'] = int(i * 0.05)
        progress['skip'] = int(i * 0.05)
        
        if i < 100:
            progress['message'] = f"[{i}/100] 正在下载图片..."
        else:
            progress['status'] = 'completed'
            progress['message'] = '下载完成: 成功90个, 失败5个, 跳过5个'
            progress['end_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(progress, f, ensure_ascii=False)
        
        # 显示进度
        percent = i
        print(f"进度: {percent}% - {progress['message']}")
    
    print("-" * 60)
    print("模拟完成!")

if __name__ == "__main__":
    simulate_download_progress()
