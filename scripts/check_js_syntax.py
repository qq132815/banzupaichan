# -*- coding: utf-8 -*-
import re
import subprocess
import os

# 读取HTML文件
with open("F:\\Codex项目文件\\班组排产系统\\templates\\schedule.html", "r", encoding="utf-8") as f:
    content = f.read()

# 提取JavaScript代码
script_pattern = r'<script>(.*?)</script>'
scripts = re.findall(script_pattern, content, re.DOTALL)

if scripts:
    # 合并所有JavaScript代码
    js_code = "\n".join(scripts)
    
    # 写入临时文件
    temp_js = "F:\\Codex项目文件\\班组排产系统\\temp_schedule.js"
    with open(temp_js, "w", encoding="utf-8") as f:
        f.write(js_code)
    
    print(f"提取了 {len(scripts)} 个脚本块")
    print(f"JavaScript代码已保存到: {temp_js}")
    
    # 使用Node.js检查语法
    try:
        result = subprocess.run(["node", "-c", temp_js], capture_output=True, text=True, encoding="utf-8")
        if result.returncode == 0:
            print("JavaScript语法检查通过！")
        else:
            print(f"JavaScript语法错误:")
            print(result.stderr)
    except Exception as e:
        print(f"检查语法时出错: {e}")
else:
    print("未找到JavaScript代码块")
