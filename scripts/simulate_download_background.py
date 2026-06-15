# -*- coding: utf-8 -*-
import json
import os
import time
import threading
from datetime import datetime

PROGRESS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "download_progress.json")

def simulate_download_in_background():
    """在后台模拟下载进度"""
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
    
    print("后台模拟下载已启动...")
    
    for i in range(101):
        time.sleep(0.1)
        
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
    
    print("后台模拟下载完成!")

if __name__ == "__main__":
    # 在后台线程运行模拟
    thread = threading.Thread(target=simulate_download_in_background)
    thread.daemon = True
    thread.start()
    
    # 主线程继续运行
    print("模拟已启动，可以通过API查询进度")
    print("按Ctrl+C退出")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n退出程序")
