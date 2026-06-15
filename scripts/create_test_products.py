# -*- coding: utf-8 -*-
import openpyxl
import os

# 创建测试数据
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "产品定义"

# 添加表头
headers = ["产品编码", "产品名称", "规格型号", "分类", "客户", "项目", "描述", "状态", "图片URL"]
ws.append(headers)

# 添加测试数据
test_data = [
    ["P001", "轴承A", "6205-2RS", "成品", "客户A", "项目A", "深沟球轴承", "active", "https://via.placeholder.com/150/FF0000"],
    ["P002", "轴承B", "6206-2RS", "成品", "客户B", "项目B", "深沟球轴承", "active", "https://via.placeholder.com/150/00FF00"],
    ["P003", "密封圈A", "SR-10x20x5", "半成品", "客户A", "项目A", "橡胶密封圈", "active", "https://via.placeholder.com/150/0000FF"],
    ["P004", "密封圈B", "SR-15x25x5", "半成品", "客户C", "项目C", "橡胶密封圈", "active", "https://via.placeholder.com/150/FFFF00"],
    ["P005", "钢球", "1/4\"", "原材料", "客户D", "项目D", "不锈钢钢球", "active", "https://via.placeholder.com/150/FF00FF"],
    ["P006", "保持架", "PC-6205", "半成品", "客户A", "项目A", "尼龙保持架", "active", "https://via.placeholder.com/150/00FFFF"],
    ["P007", "防尘盖", "ZZ-6205", "半成品", "客户B", "项目B", "金属防尘盖", "active", "https://via.placeholder.com/150/800000"],
    ["P008", "润滑脂", "LG-220", "原材料", "客户E", "项目E", "高温润滑脂", "active", "https://via.placeholder.com/150/008000"],
    ["P009", "包装盒", "BX-001", "包材", "客户F", "项目F", "纸盒包装", "active", "https://via.placeholder.com/150/000080"],
    ["P010", "标签", "LB-001", "包材", "客户F", "项目F", "产品标签", "inactive", "https://via.placeholder.com/150/808000"]
]

for row in test_data:
    ws.append(row)

# 保存文件
output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "imports", "product_definitions_test.xlsx")
os.makedirs(os.path.dirname(output_path), exist_ok=True)
wb.save(output_path)

print(f"测试数据文件已创建: {output_path}")
print(f"包含 {len(test_data)} 条测试数据")
