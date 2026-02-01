Task A：地图标注验证
# Task A: 0-25km "新激活" Tiles 地图标注与验证

## 目标
将震后新激活的 29 个 tiles 标注到交互式地图上，与已知救援设施位置对照，验证"救援营地"假说。

## 输入数据
- Population 数据: `datasets/turkiye_earthquake_2023_sample/raw/population/`
- 震中坐标: (37.174, 37.032)

## 需要提取的 tiles
震后 +16h 在 0-25km 范围内、震前不存在的 29 个 tiles：
```python
# 提取代码
pre = pd.read_csv('.../2172754818300831_2023-02-05_0800.csv')
post = pd.read_csv('.../2172754818300831_2023-02-06_0800.csv')
# 计算距离，筛选 0-25km
# new_tiles = post 中存在但 pre 中不存在的 quadkey

实现要求
A.1 生成交互式地图 (Folium)

import folium

# 创建地图，中心为震中
m = folium.Map(location=[37.174, 37.032], zoom_start=10)

# 标注震中
folium.Marker([37.174, 37.032], popup='Epicenter', icon=folium.Icon(color='red')).add_to(m)

# 标注新激活 tiles（用圆圈，大小按 n_crisis 缩放）
for _, row in new_tiles.iterrows():
    folium.CircleMarker(
        location=[row['latitude'], row['longitude']],
        radius=row['n_crisis'] / 5,  # 按人数缩放
        popup=f"n_crisis: {row['n_crisis']:.0f}",
        color='blue',
        fill=True
    ).add_to(m)

# 画 25km 半径圈
folium.Circle([37.174, 37.032], radius=25000, color='gray', dash_array='5').add_to(m)

m.save('outputs/tile_validation/new_tiles_map.html')

A.2 叠加已知地理信息（如果可获取）
土耳其机场位置（Gaziantep Airport: 36.947, 37.478）
主要医院位置
已知的救援营地/安置点（如果有公开数据）
A.3 输出

outputs/tile_validation/
├── new_tiles_map.html          # 交互式地图
├── new_tiles_coordinates.csv   # 新激活 tiles 的坐标列表
├── README.md                   # 分析说明
└── figures/
    └── new_tiles_static.png    # 静态地图截图

验证假说
如果新激活 tiles 聚集在机场/主干道/开阔地带 → 支持"救援营地"假说
如果新激活 tiles 分散在城区 → 可能是"居民聚集"而非救援
补充分析
看这些 tiles 的时间演化（+16h → +40h → +160h）
如果持续激活 → 固定设施（营地）
如果快速消失 → 临时活动（救援行动）


---

## Task B：物理模型建立

```markdown
# Task B: φ(r,t) 时空演化物理模型

## 目标
建立人口空间再分布的物理模型，用扩散方程 + 源项描述双向流动动态。

## 核心变量
- φ(r,t) = n_crisis / n_baseline：距震中距离 r、时间 t 的人口变化比
- 已有数据：`outputs/population_redistribution/tables/redistribution_by_distance_band.csv`

## 模型框架

### B.1 数据准备
```python
# 读取距离带数据
df = pd.read_csv('outputs/population_redistribution/tables/redistribution_by_distance_band.csv')

# 转换为 φ(r,t) 矩阵
# r: 距离带中心 (12.5, 37.5, 75, 150, 300 km)
# t: hours_since_quake
pivot = df.pivot_table(index='hours_since_quake', columns='distance_band', values='phi_aggregate')

B.2 观察现象特征

# 1. 绘制 φ(r) 在不同时间点的曲线
# 预期：震后早期呈现 U 形（两端高、中间低）

# 2. 绘制 φ(t) 在不同距离带的曲线  
# 预期：中间距离带（25-200km）先下降后恢复

# 3. 绘制 φ(r,t) 热力图
# 预期：看到"波"的传播特征

B.3 物理模型候选
模型 1: 简单扩散 + 源汇项

∂
ϕ
∂
t
=
D
∇
2
ϕ
+
S
(
r
,
t
)
∂t
∂ϕ
​
 =D∇ 
2
 ϕ+S(r,t)
其中：

D: 扩散系数（人口的"弥散"速度）
S(r,t): 源项（正=流入，负=流出）
S < 0 在 25-200km（疏散区）
S > 0 在 0-25km（救援涌入）和 200km+（接收区）
模型 2: 双向流动模型

∂
ϕ
∂
t
=
−
α
(
r
)
ϕ
+
β
(
r
,
t
)
∂t
∂ϕ
​
 =−α(r)ϕ+β(r,t)
其中：

α(r): 距离依赖的"流出率"
β(r,t): 距离和时间依赖的"流入率"
模型 3: 阈值模型（类似 SIR）

ϕ
(
r
,
t
)
=
ϕ
∞
(
r
)
+
[
ϕ
0
(
r
)
−
ϕ
∞
(
r
)
]
e
−
t
/
τ
(
r
)
ϕ(r,t)=ϕ 
∞
​
 (r)+[ϕ 
0
​
 (r)−ϕ 
∞
​
 (r)]e 
−t/τ(r)
 
其中：

φ_∞(r): 长期稳态
τ(r): 距离依赖的恢复时间尺度

B.4 模型拟合

from scipy.optimize import curve_fit

# 对每个距离带拟合指数恢复模型
def relaxation_model(t, phi_0, phi_inf, tau):
    return phi_inf + (phi_0 - phi_inf) * np.exp(-t / tau)

# 拟合并提取 τ(r)
for band in distance_bands:
    data = df[df['distance_band'] == band]
    popt, pcov = curve_fit(relaxation_model, data['hours_since_quake'], data['phi_aggregate'])
    # 记录 tau(r)

B.5 关键问题
τ(r) 是否随距离单调变化？
φ_∞(r) 是否回到 1？（完全恢复 vs 新稳态）
能否从 τ(r) 提取 scaling law？
B.6 输出

outputs/physical_model/
├── tables/
│   ├── phi_rt_matrix.csv           # φ(r,t) 矩阵
│   ├── relaxation_fit_by_band.csv  # 各距离带的拟合参数
│   └── tau_vs_distance.csv         # τ(r) 关系
├── figures/
│   ├── phi_vs_r_multitime.png      # φ(r) 多时间点曲线
│   ├── phi_vs_t_multiband.png      # φ(t) 多距离带曲线
│   ├── phi_rt_heatmap.png          # φ(r,t) 热力图
│   └── tau_vs_distance.png         # τ(r) scaling 关系
└── README.md

预期发现
如果 τ(r) ~ r^α 呈 power law → 有 scaling law，物理意义强
如果 τ 在中间距离带最大 → "疏散区"恢复最慢
如果 φ_∞ ≠ 1 → 灾害导致永久性人口再分布
Thought（中文）
这个模型的核心价值是：

把描述性的"φ 随距离和时间变化"转化为定量的物理模型
提取 τ(r) 作为"恢复时间尺度"，这是一个可解释的物理量
如果找到 scaling law，就有了理论深度，可以和 critical phenomena 文献对话

Task A 和 Task B 可以并行执行

Phase 1 (并行):
├── Task A: 地图标注 + 验证假说
└── Task B: φ(r,t) 模型 + τ(r) 提取

Phase 2 (依赖 Phase 1):
└── 综合两个任务的结果，确定最终叙事


---

**Implementation Plan, Task List and Thought in Chinese**

两个任务相互独立，可以并行执行。Task A 验证"救援营地"假说的真实性，Task B 建立物理框架。两者的结果将共同决定最终论文的叙事方向和期刊定位。---

**Implementation Plan, Task List and Thought in Chinese**

两个任务相互独立，可以并行执行。Task A 验证"救援营地"假说的真实性，Task B 建立物理框架。两者的结果将共同决定最终论文的叙事方向和期刊定位。