# -*- coding: utf-8 -*-
import json
import os
from datetime import datetime

PROGRESS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "download_progress.json")

# 读取当前进度
with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
    progress = json.load(f)

# 更新状态
progress['status'] = 'completed'
progress['message'] = f"下载完成: 成功{progress['success']}个, 失败{progress['fail']}个, 跳过{progress['skip']}个"
progress['end_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# 保存
with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
    json.dump(progress, f, ensure_ascii=False)

print("进度文件已更新为完成状态")
print(f"总数: {progress['total']}")
print(f"成功: {progress['success']}")
print(f"失败: {progress['fail']}")
print(f"跳过: {progress['skip']}")
