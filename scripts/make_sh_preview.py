#!/usr/bin/env python
"""开发工具：生成"标准工时+报工产能明细"子父级导出样式预览（复用 app 的真实产能算法）。"""
# -*- coding: utf-8 -*-
import sqlite3, io, os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import app as appmod
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter
import openpyxl

conn = sqlite3.connect(r"data/production.db")
conn.row_factory = sqlite3.Row
c = conn.cursor()

# 选取报工数最多、且有标准工时的 4 个 产品+工序 作父组
parents = c.execute("""
  SELECT product_code, process_name FROM work_reports
  WHERE (excluded IS NULL OR excluded=0) AND report_hours>0 AND report_qty>0
  GROUP BY product_code, process_name
  ORDER BY COUNT(*) DESC LIMIT 4
""").fetchall()
cache = appmod._load_standard_hours_cache()
data_by_key = {}
if cache:
    for r in cache['data']:
        data_by_key[(r.get('product_code',''), r.get('process_name',''))] = r
cap_max, short_hours = appmod._get_capacity_params()

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "标准工时+报工明细"
headers = ["层级", "产品编号", "产品名称", "工序", "班组", "标准工时(分)", "换线(分)", "焊点", "可用设备",
           "报工平均产能(H)", "报工最高产能(H)", "报工最低产能(H)", "真实产能(件/H)", "装框量", "报工样本数", "备注",
           "标记", "报工时间", "操作员", "工单号", "设备", "报工数量", "报工工时(H)", "合格", "不良",
           "明细产能(件/H)", "节拍(秒/件)", "有效/剔除原因"]
ws.append(headers)
thin = Side(style='thin', color='D0D5DD'); border = Border(left=thin, right=thin, top=thin, bottom=thin)
hfill = PatternFill('solid', fgColor='305496'); parent_fill = PatternFill('solid', fgColor='E8F0FE')
cmax = PatternFill('solid', fgColor='D7F5DD'); cmin = PatternFill('solid', fgColor='FDE2E2'); cinvalid = PatternFill('solid', fgColor='F5F5F5')
hfont = Font(bold=True, color='FFFFFF'); parent_font = Font(bold=True, color='1F3864')
for cell in ws[1]:
    cell.fill = hfill; cell.font = hfont; cell.border = border
    cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

for (pc, proc) in parents:
    row = data_by_key.get((pc, proc), {})
    nr = c.execute("""SELECT product_code, product_name, process_name, order_no, operator, equipment,
                      report_qty, report_hours, good_qty, bad_qty, create_time, frame_qty, excluded
                      FROM work_reports WHERE product_code=? AND process_name=? ORDER BY create_time DESC""", (pc, proc)).fetchall()
    kids = [{'product_code': r[0], 'product_name': r[1], 'process_name': r[2], 'order_no': r[3],
             'operator': r[4], 'equipment': r[5], 'report_qty': r[6], 'report_hours': r[7],
             'good_qty': r[8], 'bad_qty': r[9], 'create_time': r[10], 'frame_qty': r[11], 'excluded': r[12]} for r in nr]
    true_cap, kids = appmod.compute_true_capacity(kids, capacity_physical_max=cap_max, short_hours=short_hours)
    pname = row.get('product_name') or (kids[0]['product_name'] if kids else pc)
    valid_count = sum(1 for k in kids if k.get('valid') and k.get('capacity') > 0)
    r0 = ws.max_row + 1
    ws.append(["标准工时汇总", pc, pname, proc, row.get('team_name','') or '',
               row.get('standard_hours', 0) or 0, row.get('setup_time', 0) or 0,
               row.get('weld_count', 0) or 0, row.get('available_equipment','') or '',
               row.get('report_avg', 0), row.get('report_max', 0), row.get('report_min', 0), true_cap,
               row.get('frame_qty','') or '', valid_count, row.get('remark','') or '', None] + [None]*11)
    for cell in ws[r0]:
        cell.fill = parent_fill; cell.font = parent_font; cell.border = border
    for kid in kids:
        ws.append(["报工明细", pc, pname, proc, row.get('team_name','') or '', None] + [None]*10 +
                  (["最高" if kid.get('is_max') else ("最低" if kid.get('is_min') else ""),
                    kid['create_time'] or '', kid['operator'] or '', kid['order_no'] or '',
                    kid['equipment'] or '', kid['report_qty'] or 0, kid['report_hours'] or 0,
                    kid['good_qty'] or 0, kid['bad_qty'] or 0,
                    kid['capacity'] if kid.get('capacity') else '',
                    kid['takt'] if kid.get('takt') else '',
                    ('有效' if kid.get('valid') else ('剔除·' + kid['reason']))]))
        r = ws.max_row
        if kid.get('is_max'): f = cmax; col = '15803D'
        elif kid.get('is_min'): f = cmin; col = 'B91C1C'
        elif not kid.get('valid'): f = cinvalid; col = '6B7280'
        else: f = None; col = '000000'
        for cell in ws[r]:
            cell.border = border
            if f: cell.fill = f
            if col != '000000': cell.font = Font(color=col)

widths = [10, 16, 26, 16, 8, 11, 9, 9, 15, 13, 13, 13, 13, 9, 10, 30, 8, 19, 10, 14, 12, 9, 11, 8, 8, 13, 11, 22]
for i, w in enumerate(widths, 1):
    ws.column_dimensions[get_column_letter(i)].width = w
ws.freeze_panes = "A2"; ws.row_dimensions[1].height = 26
for r in range(2, ws.max_row + 1):
    if ws.cell(r, 1).value == "报工明细":
        ws.row_dimensions[r].outline_level = 1
ws.sheet_properties.outlinePr.summaryBelow = False

out = "exports/标准工时报工明细_导出样式.xlsx"
wb.save(out)
print("saved:", os.path.abspath(out), "rows:", ws.max_row, "cols:", ws.max_column)
conn.close()