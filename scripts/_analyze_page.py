"""保存完整数据集目录"""
import sys, io, json, csv
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 从之前浏览器提取的数据（直接硬编码结果）
with open("datasets_catalog.json", "r", encoding="utf-8") as f:
    datasets = json.load(f)

print(f"目录中共 {len(datasets)} 个数据集")

# 按事件名去重统计
events = {}
for ds in datasets:
    name = ds["name"]
    if name not in events:
        events[name] = {"types": [], "countries": ds["countries"], "dateStart": ds.get("dateStart", ds.get("date_start","")), "dateEnd": ds.get("dateEnd", ds.get("date_end",""))}
    events[name]["types"].append(ds["type"])

print(f"\n独立灾难事件: {len(events)}")
print()
for i, (name, info) in enumerate(sorted(events.items()), 1):
    types_str = " | ".join(sorted(set(info["types"])))
    print(f"  {i:2d}. {name}")
    print(f"      国家: {info['countries']} | 日期: {info['dateStart']} ~ {info['dateEnd']}")
    print(f"      数据类型: {types_str}")
    print()
