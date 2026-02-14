# Disaster Recovery Dynamics 文献检索与梳理（覆盖 2023–2026，高影响期刊优先）

检索聚焦你列出的 6 个“必须覆盖主题”。整体结论先给在前面：  
1) **“灾后 mobility network 的渗流/临界性”**在交通/道路网络里有人用渗流做“脆弱性阈值”分析，但**直接把“灾后人类流动网络（OD/共现/移动）”做成渗流相变并讨论恢复过程的工作仍然稀缺**；现有研究更多停留在网络指标/多尺度结构变化与韧性曲线。:contentReference[oaicite:0]{index=0}  
2) **“恢复时间尺度与标度律”**：大量工作会估计恢复时间/韧性曲线参数，但你关心的 **τ(r)** 或 **τ(L)**（随空间尺度/距离/系统尺度的标度关系）在灾后流动领域**尚未形成成熟、可复用的统一框架**，非常可能是“可打”的 gap。:contentReference[oaicite:1]{index=1}  
3) **“灾难是否改变扩散特性”**：已有证据表明灾前的“位移/回转半径”等统计规律在灾中仍可用幂律/截断幂律刻画，但参数（如幂指数、截断尺度）会显著变化，可作为“扩散机制改变”的定量入口。:contentReference[oaicite:2]{index=2}  
4) **Meta/Facebook Disaster Maps（含 Data for Good）**在 2023–2026 的学术实证并不算多，但已出现：用 Facebook 聚合位置数据估计社区韧性/恢复时间、与运营商话单数据对比验证、以及在地震/野火情境下讨论时空分辨率与偏差等。:contentReference[oaicite:3]{index=3}  
5) **2023 土耳其—叙利亚地震**：最接近“直接竞争者”的公开高质量学术论文之一是 EPJ Data Science 2025 的 CDR 位移检测新方法（ASA），对“地震后位移模式”给出了很具体的方法创新；但**用 Meta/FBDM 直接做统计物理式的“恢复标度/普适律”仍未看到成熟成品**。:contentReference[oaicite:4]{index=4}  
6) **非平衡弛豫在社会/经济系统**：金融网络冲击传播与弛豫（2025 Chaos）等提供了“外部扰动—传播—回稳”的可迁移建模语言；把灾难视为“quench”，用可观测 order parameter（网络连通性、位移统计量、空间相关长度等）做弛豫动力学，是你们定位的强支撑点。:contentReference[oaicite:5]{index=5}  


---

## 1. 灾后流动网络的临界性/渗流  
关键词：`"disaster" + "mobility network" + (percolation OR critical transition OR phase transition)`  
目标问题：是否有人做过灾后 mobility network 的渗流分析？

### 结论（针对你的问题）
- **“渗流/临界”更多出现在道路/交通网络脆弱性分析**（例如洪涝导致的网络功能突变、阈值行为），但把“人类流动网络（由手机/GPS/平台数据构建）”在灾后做成严格的渗流相变框架、并进一步讨论恢复过程临界性/临界减速的论文仍不多。:contentReference[oaicite:6]{index=6}  
- 有研究明确指出：**仅用渗流刻画物理网络受损，并不能充分解释交通系统“功能”（如旅行时间）受灾扰动的时空传播与持续时间**——这直接指向你们可以把“渗流 + 功能态（travel-time / mobility-flow）+ 恢复弛豫”融合起来做新贡献。:contentReference[oaicite:7]{index=7}  

### 核心文献（建议优先读）

#### [1] Percolation transitions in urban mobility networks: Early warnings for critical transitions
**基本信息：**
- 作者：Emad A. Emamgholizadeh 等（et al.）
- 期刊：Sustainable Cities and Society
- 年份：2023
- DOI/链接：10.1016/j.scs.2023.104928 :contentReference[oaicite:8]{index=8}  

**核心内容：**
- 研究问题：城市出行网络是否存在渗流转变？能否提供“临界转变”的早期预警信号？
- 使用数据：城市 mobility network（论文以“城市出行网络”为对象，具体数据源以原文为准）
- 核心方法：渗流分析 + 临界转变/预警信号视角（early warning）
- 主要发现：报告了 mobility network 的渗流转变现象，并讨论用于识别临界转变的预警思路。:contentReference[oaicite:9]{index=9}  

**与本研究关系：**
- 可借鉴：把“mobility network”直接放进渗流/临界框架、做临界阈值与预警指标。
- 差异点：未必聚焦“灾后恢复弛豫与标度”，且不一定使用 Meta/FBDM。
- 我们的潜在创新：把灾难冲击作为外部扰动（quench），在灾前/灾中/灾后网络上测 **临界阈值漂移**、**关联长度/巨分量恢复** 的时间标度，并与空间尺度 L 建立 τ(L) 关系。

**关键图/表：**
- 建议重点看：阈值识别、巨分量/连通性随参数变化、预警指标（若有）。

**引用价值：** ⭐⭐⭐⭐

---

#### [2] Anatomy of perturbed traffic networks during urban flooding
**基本信息：**
- 作者：以原文为准
- 期刊：Sustainable Cities and Society（ScienceDirect 页面）
- 年份：2023（以页面信息为准）
- DOI/链接：链接见引用（ScienceDirect）:contentReference[oaicite:10]{index=10}  

**核心内容：**
- 研究问题：洪涝如何扰动交通网络？影响是否局限在淹没区域？影响持续多久？
- 使用数据：交通/出行网络与洪涝扰动背景（细节以原文为准）
- 核心方法：讨论并对比“渗流方法”对交通系统影响刻画的局限；强调旅行时间等功能指标的重要性
- 主要发现：明确指出“渗流能量化受损程度，但对交通系统功能与时空持续扰动解释不足”，提示研究空白。:contentReference[oaicite:11]{index=11}  

**与本研究关系：**
- 可借鉴：把“结构性受损（渗流）”与“功能性受损（travel time / mobility flow）”区分开，并讨论灾后持续时间。
- 差异点：不一定使用社交平台 mobility；更偏交通系统。
- 我们的潜在创新：在 Meta/FBDM 的人类流动网络上构造“功能态 order parameter”（例如 OD 强度、有效连通性、可达性 proxy），建立结构-功能耦合的临界性解释。

**关键图/表：**
- 建议重点看：关于渗流局限性与“持续时间/空间外溢”的讨论段落。

**引用价值：** ⭐⭐⭐⭐

---

#### [3] Modest flooding can trigger catastrophic road network disruption
**基本信息：**
- 作者：以原文为准
- 期刊：Communications Earth & Environment
- 年份：2022（经典/近邻参考）
- DOI/链接：链接见引用（Nature Portfolio）:contentReference[oaicite:12]{index=12}  

**核心内容：**
- 研究问题：洪涝是否存在“小扰动触发系统级交通网络灾变”的阈值行为？
- 核心方法：道路网络破坏/中断与系统级连通性、可能含渗流/阈值思想
- 主要发现：强调洪涝触发“灾变式”网络中断的可能性。:contentReference[oaicite:13]{index=13}  

**与本研究关系：**
- 可借鉴：阈值/灾变叙事与“临界性”语言。
- 我们的潜在创新：把阈值行为从“道路网络”迁移到“人类流动网络 + 恢复弛豫”。

**引用价值：** ⭐⭐⭐

---

## 2. 灾后恢复的时间尺度与标度律  
关键词：`"disaster recovery" + (scaling law OR power law OR relaxation time) + mobility`  
目标问题：τ(r) 或 τ(L) 的标度关系是否被研究过？

### 结论（针对你的问题）
- 2023–2026 年的主流做法是：用“韧性曲线/恢复时间/损失-恢复参数”刻画灾后 mobility 或活动强度的回稳；也有人用更“过程化”的点过程/状态切换模型估计恢复率。:contentReference[oaicite:14]{index=14}  
- 但你要的 **τ 随空间尺度/距离/系统尺寸的标度律（τ(r)、τ(L)）**：我在本轮检索到的核心论文里，没有看到已经被“系统总结 + 可复用地验证为普适律”的成熟答案；更像是“大家都在算 recovery time，但还没把它变成标度理论”。这非常像你们的潜在创新位点。:contentReference[oaicite:15]{index=15}  

### 核心文献（建议优先读）

#### [4] Understanding the loss in community resilience due to hurricanes using Facebook Data
**基本信息：**
- 作者：Tasnuba Binte Jamal；Samiul Hasan
- 期刊：International Journal of Disaster Risk Reduction
- 年份：2023
- DOI/链接：10.1016/j.ijdrr.2023.104036 :contentReference[oaicite:16]{index=16}  

**核心内容：**
- 研究问题：能否用 Facebook 聚合位置/人口活动数据量化飓风造成的社区韧性损失与恢复时间？
- 使用数据：Facebook 聚合位置数据（灾前/灾中/灾后活动水平）:contentReference[oaicite:17]{index=17}  
- 核心方法：将韧性定义为“冲击幅度 + 恢复时间”的函数；用基础设施中断、灾害条件、社会经济因素解释差异
- 主要发现：恢复时间与韧性损失可被系统量化；电力/交通中断与社会经济差异与韧性损失相关。:contentReference[oaicite:18]{index=18}  

**与本研究关系：**
- 可借鉴：用平台聚合数据定义“恢复时间尺度”的可操作方法；把恢复时间与外部因素关联解释。
- 差异点：不以统计物理标度律为主线；未必讨论 τ(L)/τ(r)。
- 我们的潜在创新：在其“恢复时间”基础上，进一步引入空间尺度（网格尺度/到震中距离/行政层级 L）与 τ 的系统关系，并跨灾种验证。

**关键图/表：**
- 重点找：韧性函数定义、恢复时间估计、因素回归解释。

**引用价值：** ⭐⭐⭐⭐

---

#### [5] Modelling social mobility disruptions and recovery during disasters: A mobile phone data approach
**基本信息：**
- 作者：Minh Kieu；Alexis Comber；Thanh Bui Quang；Nick Malleson
- 期刊：International Journal of Disaster Risk Reduction
- 年份：2025
- DOI/链接：10.1016/j.ijdrr.2025.105812 :contentReference[oaicite:19]{index=19}  

**核心内容：**
- 研究问题：如何用移动电话数据对“扰动—恢复”进行过程建模（不仅是算一个恢复天数）？
- 使用数据：移动电话数据（保密）:contentReference[oaicite:20]{index=20}  
- 核心方法：Hawkes 点过程（含状态切换/恢复过程建模的取向，细节以原文为准）
- 主要发现：提供了一种把“灾害期间的出行扰动与恢复”参数化的建模路线，为定义“恢复率/恢复时间常数”提供工具。:contentReference[oaicite:21]{index=21}  

**与本研究关系：**
- 可借鉴：用过程模型把“恢复”变成可拟合参数（可对应弛豫时间）。
- 差异点：未必强调标度律与普适性。
- 我们的潜在创新：把模型拟合出的恢复参数映射到空间尺度（网格/距离/系统尺寸）并检验 τ(L) 标度。

**关键图/表：**
- 重点看：模型结构、参数含义、恢复率/恢复阶段的识别方式。

**引用价值：** ⭐⭐⭐⭐

---

#### [6] Dissecting resilience curve archetypes and properties in human mobility resilience curves
**基本信息：**
- 作者：以原文为准
- 期刊：Scientific Reports
- 年份：2025
- DOI/链接：10.1038/s41598-025-92056-0   

**核心内容：**
- 研究问题：人类流动的韧性曲线是否存在“典型形态（archetypes）”？曲线性质如何系统比较？
- 方法：韧性曲线形态分类/性质分析（细节以原文为准）
- 主要发现：把“恢复轨迹”从零散个案，推进到可比较的形态学层面。  

**与本研究关系：**
- 可借鉴：韧性曲线表征与分类框架，可作为你们定义 order parameter 的候选。
- 我们的潜在创新：把 archetype 进一步与临界性、弛豫机制、空间尺度联系起来，寻求普适标度。

**引用价值：** ⭐⭐⭐

---

## 3. 灾后人类流动的扩散特性  
关键词：`"disaster" + "human mobility" + (diffusion OR Lévy flight OR MSD OR anomalous diffusion)`  
目标问题：灾难是否改变人类流动的扩散特性？

### 结论（针对你的问题）
- 以“位移分布/回转半径”等扩散 proxy 来看，灾难期间统计规律常仍可用（截断）幂律拟合，但**幂指数与截断尺度会变化**，支持“扩散机制/可达性约束改变”的解释路径。:contentReference[oaicite:24]{index=24}  
- 近期工作还把网络结构（宏观指标 + motifs）纳入灾前/灾中/灾后对比，有利于把“扩散变化”与“网络结构重组”挂钩。:contentReference[oaicite:25]{index=25}  

### 核心文献（建议优先读）

#### [7] Returners and explorers dichotomy in the face of natural hazards: evidence from human mobility patterns during Hurricane Ian
**基本信息：**
- 作者：Jianhe He 等（et al.）
- 期刊：Scientific Reports
- 年份：2024
- DOI/链接：链接见引用（Scientific Reports 页面）:contentReference[oaicite:26]{index=26}  

**核心内容：**
- 研究问题：自然灾害（飓风）下，人类流动模式如何变化？“returners vs explorers”是否仍成立？
- 使用数据：飓风 Ian 期间的人类出行数据（论文使用“人类流动模式”数据，细节以原文为准）:contentReference[oaicite:27]{index=27}  
- 核心方法：位移分布与回转半径分布的统计拟合（文中报告截断幂律形式与参数）:contentReference[oaicite:28]{index=28}  
- 主要发现：灾中位移分布仍可用截断幂律拟合，但参数（如幂指数 α 与截断 λ）与灾前不同；回转半径也出现统计变化。:contentReference[oaicite:29]{index=29}  

**与本研究关系：**
- 可借鉴：把扩散 proxy（位移、回转半径）用统一分布族拟合，并用参数变化刻画灾害影响。
- 差异点：未必把“恢复过程”提升到标度/普适律层面。
- 我们的潜在创新：把参数变化与恢复弛豫时间常数联系；进一步做空间分层（到震中距离/网格尺度）看参数与 τ 的耦合标度。

**关键图/表：**
- Fig. 1：位移分布拟合与参数变化（文中明确讨论截断幂律与参数）。:contentReference[oaicite:30]{index=30}  

**引用价值：** ⭐⭐⭐⭐

---

#### [8] Unraveling hurricane Ian’s Impact: A multiscale analysis of mobility networks in Florida
**基本信息：**
- 作者：Jinpeng Wang；Yujie Hu
- 期刊：Transportation Research Part D: Transport and Environment
- 年份：2024
- DOI/链接：10.1016/j.trd.2024.104482 :contentReference[oaicite:31]{index=31}  

**核心内容：**
- 研究问题：飓风对 mobility network 的冲击与恢复，在宏观网络指标与 motif 局部结构层面分别如何体现？
- 使用数据：隐私保护的手机 GPS 数据（Cuebiq），构建灾前/灾中/灾后 mobility networks :contentReference[oaicite:32]{index=32}  
- 核心方法：宏观网络指标（密度、平均路径长度、聚类系数、模块度、鲁棒性等）+ motif 结构与空间分布演化
- 主要发现：灾中网络连通性/效率显著下降，灾后迅速恢复；不同 motif 类型响应不同，揭示局部脆弱性与适应。:contentReference[oaicite:33]{index=33}  

**与本研究关系：**
- 可借鉴：多尺度（macro + motif）框架非常贴近你们“统计物理 × 网络”的路线；可作为 order parameter 候选池。
- 差异点：未必讨论渗流临界或 τ(L) 标度。
- 我们的潜在创新：在其网络指标时间序列上做“临界减速/弛豫拟合”，并跨空间尺度/网格聚合检验 τ(L)。

**关键图/表：**
- Fig. 4：宏观网络指标随时间变化（文中提到按时间序列比较）。:contentReference[oaicite:34]{index=34}  

**引用价值：** ⭐⭐⭐⭐

---

#### [9] Resilience patterns of human mobility in response to extreme events
**基本信息：**
- 作者：以原文为准
- 期刊：National Science Review
- 年份：2023
- DOI/链接：链接见引用（NSR 页面）:contentReference[oaicite:35]{index=35}  

**核心内容：**
- 研究问题：极端事件下，人类流动韧性是否呈现可归纳的响应模式？
- 方法与发现：系统比较“极端事件—流动响应—韧性”模式（细节以原文为准）:contentReference[oaicite:36]{index=36}  

**与本研究关系：**
- 可借鉴：跨事件归纳“韧性模式”的思路，便于你们做普适性对比。
- 我们的潜在创新：把“模式”升级为“标度律/临界行为”，并用 Meta/FBDM 做可重复的网格化测量。

**引用价值：** ⭐⭐⭐

---

## 4. Meta/Facebook Disaster Maps 的最新实证（2023–2026）  
关键词：`"Facebook Disaster Maps" OR "Meta Disaster Maps" + 2023-2026`  
目标问题：目前用 FBDM 做了哪些分析？gap 在哪？

### 结论（针对你的问题）
- 2023–2026 期间，学术论文中出现了多条“Meta 数据/ Facebook 聚合位置数据”的使用路径：  
  1) **直接用 Facebook 聚合位置数据量化灾害冲击与恢复时间**（社区韧性/恢复时间）。:contentReference[oaicite:37]{index=37}  
  2) **用运营商话单（XDR/CDR）做高分辨率基准，再与 FBDM 做可比性验证**，并指出 FBDM 的时空分辨率限制与生成时点限制。:contentReference[oaicite:38]{index=38}  
  3) **在地震情境用 Meta Data for Good 的“Movement between tiles / administration levels”等产品**分析灾后移动模式。:contentReference[oaicite:39]{index=39}  
  4) **专门讨论 Meta 数据的偏差/代表性问题**（即便不在灾害场景，也直接影响你们对 FBDM 的方法学论证）。:contentReference[oaicite:40]{index=40}  
- 目前最明显的 gap：  
  - 很多论文停在“描述性指标/恢复时间估计/社会经济差异”，**少有把 FBDM 当作统计物理对象去做“弛豫动力学 + 临界性 + 标度律”**的系统研究。:contentReference[oaicite:41]{index=41}  

### 核心文献（建议优先读）

#### [10] Understanding the loss in community resilience due to hurricanes using Facebook Data
（同 [4]，这里作为“FBDM/Meta 聚合位置数据实证”代表作再次归类）:contentReference[oaicite:42]{index=42}  

---

#### [11] Evacuation patterns and socioeconomic stratification in the context of wildfires
**基本信息：**
- 作者：T. Naushirvanov 等（et al.）
- 期刊：EPJ Data Science
- 年份：2025
- DOI/链接：链接见引用（EPJ Data Science 页面）:contentReference[oaicite:43]{index=43}  

**核心内容：**
- 研究问题：野火疏散期间，不同社会经济群体的夜间停留与迁移距离如何变化？以及运营商数据能否与 FBDM 对比？
- 使用数据：高分辨率移动通信记录（智利 Valparaíso 2024 野火）；并与 Facebook Disaster Maps 做可比性讨论 :contentReference[oaicite:44]{index=44}  
- 核心方法：回归断点 + DID 的因果推断组合，分解野火冲击；比较社会经济分层差异
- 主要发现：低社会经济群体离家时间更长；整体夜间迁移距离下降；并指出 FBDM **时间分辨率较粗且仅在野火发生后生成**，但具备一定可比性。:contentReference[oaicite:45]{index=45}  

**与本研究关系：**
- 可借鉴：把 FBDM 与更高分辨率数据对齐验证的范式；对 FBDM 局限性的“可引用论据”很关键。
- 差异点：研究对象是野火疏散与社会经济分层，不是统计物理标度。
- 我们的潜在创新：同样做“FBDM vs 更高分辨率数据/其他数据源”的验证，同时把验证嵌入“标度律/临界性”的主线。

**关键图/表：**
- 重点找：关于 FBDM 可比性与时间分辨率限制的讨论段。:contentReference[oaicite:46]{index=46}  

**引用价值：** ⭐⭐⭐⭐

---

#### [12] The movement pattern changes of population following a disaster: Example of the Aegean Sea earthquake of October 2020
**基本信息：**
- 作者：Cigdem Varol 等（et al.）
- 期刊：ScienceDirect 页面（期刊为灾害风险相关方向，详见原文）
- 年份：2024
- DOI/链接：链接见引用（ScienceDirect）:contentReference[oaicite:47]{index=47}  

**核心内容：**
- 研究问题：地震后城市内/城市间移动模式如何恢复？与余震活动是否同步？
- 使用数据：Meta Data for Good 的 movement between tiles / administration levels 等产品；并用公共交通使用辅助解释 :contentReference[oaicite:48]{index=48}  
- 核心方法：多尺度（省/区/网格 tile）对比灾前/灾后移动与距离；对齐余震与出行变化
- 主要发现：震后短期内出行距离与城市内移动模式变化明显，随后逐步回到“新常态”；不同尺度的恢复时长不同。:contentReference[oaicite:49]{index=49}  

**与本研究关系：**
- 可借鉴：直接使用 Meta Data for Good 产品做“震后恢复时长”的定量估计与多尺度拆分。
- 差异点：案例是 2020 地震，不是 2023；也未强调标度律/临界性。
- 我们的潜在创新：迁移到 2023 Türkiye 地震，用同样的数据产品但采用统计物理框架（弛豫/扩散/临界性）。

**关键图/表：**
- 重点找：不同尺度的恢复时长与距离分布变化图。

**引用价值：** ⭐⭐⭐

---

#### [13] Bias in mobility datasets drives divergence in modeled outbreak dynamics
**基本信息：**
- 作者：T. Chin 等（et al.）
- 期刊：Communications Medicine
- 年份：2024/2025（Nature Portfolio 页面，详见原文）
- DOI/链接：链接见引用（Communications Medicine）:contentReference[oaicite:50]{index=50}  

**核心内容：**
- 研究问题：不同移动数据源（多家运营商 CDR vs Meta Data for Good）在建模中会导致多大偏差？
- 使用数据：孟加拉国三家运营商 CDR + Meta Data for Good（Movement Between Tiles/Population 等）:contentReference[oaicite:51]{index=51}  
- 核心方法：对比流动矩阵差异；用 metapopulation 模型评估对传播模拟结果的影响
- 主要发现：单一运营商或不同数据源存在结构性偏差；Meta 数据捕捉的人群（智能手机、安装应用、开启定位历史）与 CDR 人群不同，可能影响结论。:contentReference[oaicite:52]{index=52}  

**与本研究关系：**
- 可借鉴：你们写“数据局限性/偏差讨论”时的关键引用；也可指导你们做“偏差敏感性分析”。
- 我们的潜在创新：把偏差讨论从“传播建模”迁移到“灾后恢复标度/临界性”推断的稳健性检验。

**关键图/表：**
- 重点找：Meta Data for Good 数据定义、与 CDR 对比结果、偏差对模型输出影响。

**引用价值：** ⭐⭐⭐⭐

---

#### [14] Wildfire Evacuation Analysis Using Facebook Data: Evidence from Palisades and Eaton Fires
**基本信息：**
- 作者：Shangkun Jiang 等（et al.）
- 期刊：arXiv（预印本）
- 年份：2026
- DOI/链接：10.48550/arXiv.2601.01052 :contentReference[oaicite:53]{index=53}  

**核心内容：**
- 研究问题：如何用 Facebook 高分辨率聚合数据构建疏散评估指标体系（遵从率、出发延迟、OD 流等）？
- 主要发现：提出指标框架与“Damage-Evacuation Disparity Index (DEDI)”用于识别“高损伤但低疏散遵从”区域。:contentReference[oaicite:54]{index=54}  

**与本研究关系：**
- 可借鉴：指标体系化、与脆弱性/风险指标耦合的写法。
- 差异点：预印本；且主线是疏散评估，不是恢复标度/普适律。
- 我们的潜在创新：将“疏散—恢复”统一进弛豫/相变框架，并跨灾种提炼标度律。

**引用价值：** ⭐⭐⭐（方法参考，注意期刊状态）

---

## 5. 2023 土耳其地震的流动性研究  
关键词：`"Turkey earthquake 2023" + (mobility OR displacement OR migration)`  
目标问题：直接竞争者有谁？用了什么数据和方法？

### 结论（针对你的问题）
- 在公开、可核查且与“位移/流动性定量分析”高度贴合的 2023–2026 学术论文中，**EPJ Data Science 2025 的 ASA（Activity Space Approach）**是非常接近“直接竞争”的一篇：它针对 2023 Türkiye–Syria 地震提出了位移检测方法创新，并用 CDR 给出细粒度空间洞察，且明确说明传统“home location”方法的局限。:contentReference[oaicite:55]{index=55}  
- 与此同时，面向应急响应的组织（如 CrisisReady/ReliefWeb）在 2023 年就使用 Meta 数据进行描述性监测，但这类多为报告/平台输出，与你们要做的“高水平学术论文 + 统计物理框架”之间仍有距离。:contentReference[oaicite:56]{index=56}  

### 核心文献（建议优先读）

#### [15] A novel activity space approach to discover displacement patterns via mobile phone data: an analysis of the 2023 Türkiye-Syria earthquakes
**基本信息：**
- 作者：Bilgeçağ Aydoğdu 等（et al.）
- 期刊：EPJ Data Science
- 年份：2025
- DOI/链接：10.1140/epjds/s13688-025-00572-8 :contentReference[oaicite:57]{index=57}  

**核心内容：**
- 研究问题：如何用 CDR 更可靠地检测地震引发的人口位移？如何避免仅依赖“home location”导致的偏差？
- 使用数据：匿名化、按小时聚合的 CDR（127,700 人），并结合受灾地区的定性田野洞察 :contentReference[oaicite:58]{index=58}  
- 核心方法：提出 Activity Space Approach（ASA），把位移检测从“家”扩展到“习惯活动空间”
- 主要发现：ASA 可提供更细的空间洞察，克服传统方法的关键局限；并能区分不同群体（含难民群体）的位移结果（细节以原文为准）。:contentReference[oaicite:59]{index=59}  

**与本研究关系：**
- 可借鉴：位移检测方法学（你们若做 displacement/return 相关分析，这篇几乎必读）；也可作为“对比基线/方法对照实验”。
- 差异点：它的主创新是位移检测方法；未必走“统计物理普适标度/临界性”路线。
- 我们的潜在创新：  
  1) 用 Meta/FBDM 做更大范围、可跨灾种复用的“标度/临界”测量；  
  2) 把“位移检测”与“恢复弛豫（τ）”统一进同一理论框架；  
  3) 做 τ(r)/τ(L) 与临界阈值漂移的系统验证。

**关键图/表：**
- 重点找：ASA 定义、与 home-based 方法对照、位移热点/时间演化图。

**引用价值：** ⭐⭐⭐⭐⭐（就“Türkiye 2023 + 位移方法”而言非常关键）

---

#### [16]（报告/平台类，非期刊论文）Mobility Data Shows Movement Away from Some Urban Areas After Deadly Earthquake
**基本信息：**
- 作者/机构：Direct Relief（新闻/报告口径）
- 年份：2023
- 链接：见引用 :contentReference[oaicite:60]{index=60}  

**用途定位：**
- 不作为学术核心引用，但可用来：对照“应急实践如何用 Meta 数据”，以及为论文动机/应用价值写作提供背景。

**引用价值：** ⭐⭐

---

## 6. 非平衡弛豫在社会/经济系统的应用  
关键词：`("non-equilibrium" OR "relaxation dynamics") + (social OR economic OR urban) ...`  
目标问题：统计物理框架在社会系统的先例有哪些？

### 结论（针对你的问题）
- 近年的一个清晰方向是：把社会/经济系统表示成（时间）网络，在外部冲击后研究“传播 + 回稳（relaxation）”，并讨论网络结构如何影响弛豫速度与冲击扩散范围。:contentReference[oaicite:61]{index=61}  
- 这类工作可以直接为你们提供“灾难 = 外部冲击/淬火（quench）”“恢复 = 弛豫动力学”的写作与建模语言；你们只需要把状态变量从“金融节点 fitness”等换成“mobility order parameter（连通性/OD 强度/扩散参数/空间相关长度）”。:contentReference[oaicite:62]{index=62}  

### 核心文献（建议优先读）

#### [17] Modeling shock propagation and resilience in financial temporal networks
**基本信息：**
- 作者：F. Lillo 等（et al.）（以论文为准）
- 期刊：Chaos
- 年份：2025
- DOI/链接：10.1063/5.0244665 :contentReference[oaicite:63]{index=63}  

**核心内容：**
- 研究问题：冲击在时间网络中如何传播？网络结构/时序如何影响冲击强度与恢复（relaxation）？
- 使用数据/模型：时间网络 + 平均场/解析推导取向（细节以原文为准）:contentReference[oaicite:64]{index=64}  
- 核心方法：显式讨论“relaxation dynamics”、比较静态、解析表达与参数敏感性
- 主要发现：网络结构（如密度等）影响冲击传播与弛豫速度；给出可解析/可计算的韧性度量思路。:contentReference[oaicite:65]{index=65}  

**与本研究关系：**
- 可借鉴：用“弛豫时间/恢复函数”作为核心对象的建模语言；结构参数如何进入 τ。
- 差异点：领域是金融网络，不是灾后人口流动。
- 我们的潜在创新：把其框架迁移到 mobility network，提出可观测 order parameter，并检验 τ(L) 标度与临界行为。

**引用价值：** ⭐⭐⭐⭐

---

#### [18] Dynamics of post-disaster recovery in behavior-dependent business networks
**基本信息：**
- 作者：以原文为准
- 期刊：Humanities and Social Sciences Communications
- 年份：2025
- DOI/链接：链接见引用（Nature Portfolio 页面）:contentReference[oaicite:66]{index=66}  

**核心内容：**
- 研究问题：行为依赖的商业网络如何在灾后恢复？  
- 方法：网络/扩散/恢复过程建模取向（细节以原文为准）:contentReference[oaicite:67]{index=67}  

**与本研究关系：**
- 可借鉴：把“恢复”作为网络动力学问题而非单一指标。
- 我们的潜在创新：将其扩展到“人类流动网络”，并引入统计物理的临界性与标度验证。

**引用价值：** ⭐⭐⭐

---

## 跨主题 Gap 分析与定位建议（回答你要的 4 个反馈问题）

### 1) 是否存在直接竞争工作？
- **在“2023 Türkiye–Syria 地震 + 位移/流动定量”层面**：EPJ Data Science 2025 的 ASA 方法论文非常接近直接竞争者（方法创新很明确）。:contentReference[oaicite:68]{index=68}  
- **在“Meta/FBDM + 灾后恢复时间”层面**：IJDRR 2023（飓风）已用 Facebook 数据做“恢复时间/韧性量化”。:contentReference[oaicite:69]{index=69}  
- **在“统计物理（临界/渗流/标度）+ 灾后恢复 + Meta/FBDM”这一交叉靶心层面**：本轮检索未看到成熟、直接对标你们“普适标度律/临界性 + FBDM”的高水平成品，更像是“有零件、缺整机”。:contentReference[oaicite:70]{index=70}  

### 2) 创新空间在哪里？
- 数据层面：  
  - 把 Meta/FBDM 与其它数据源（CDR/GPS/夜光/基础设施中断）做**系统对照与偏差敏感性分析**，避免“数据偏差导致的假标度”。:contentReference[oaicite:71]{index=71}  
- 方法层面：  
  - 将灾害视为 quench：对 mobility order parameter 做 **弛豫拟合（指数/拉伸指数/幂律恢复）**，并对不同空间聚合尺度 L 的 τ(L) 做系统检验；  
  - 将网络临界性引入：测试“巨分量/连通性/有效可达性”的阈值漂移与临界减速。:contentReference[oaicite:72]{index=72}  
- 问题层面：  
  - 现有多是“恢复时间是多少/谁更脆弱”，你们可以主打“**恢复是否存在普适标度律**、**临界行为是否可重复出现**、**灾种之间是否同一普适类**”。

### 3) 潜在合作/对比机会？
- 研究组/方向（从论文线索看）：  
  - 做 mobility 韧性曲线、网络 motifs、灾后恢复建模的一些团队（例如多篇 Scientific Reports/相关期刊上的作者群）很可能是对话对象。:contentReference[oaicite:73]{index=73}  
- 对比灾害数据：  
  - 飓风、洪涝、野火在文献中更常见，适合做“跨灾种普适性检验”的对照组；Türkiye 地震可作为强冲击案例。:contentReference[oaicite:74]{index=74}  

### 4) 最需要关注的理论工作？
- “渗流/临界转变在 mobility network”的切入（为临界性建模提供直接先例）。:contentReference[oaicite:75]{index=75}  
- “渗流不足以解释功能扰动”的反面论据（帮助你们把研究问题从结构推向功能与弛豫）。:contentReference[oaicite:76]{index=76}  
- “冲击传播—弛豫—韧性”的时间网络框架（为非平衡叙事提供跨域支撑）。:contentReference[oaicite:77]{index=77}  

---

## 你下一步最省力的“必读清单”（按你项目靶心排序）
1) Aydoğdu et al., EPJ Data Science 2025（Türkiye–Syria 地震位移检测方法，直接竞争）:contentReference[oaicite:78]{index=78}  
2) Jamal & Hasan, IJDRR 2023（Facebook 数据量化灾后恢复时间/韧性）:contentReference[oaicite:79]{index=79}  
3) Emamgholizadeh et al., SCS 2023（mobility network 渗流转变/临界预警）:contentReference[oaicite:80]{index=80}  
4) Kieu et al., IJDRR 2025（用点过程/过程模型刻画扰动—恢复）:contentReference[oaicite:81]{index=81}  
5) Wang & Hu, TRD 2024（灾前/灾中/灾后 mobility network 多尺度指标与 motifs）:contentReference[oaicite:82]{index=82}  
6) Chin et al., Communications Medicine（Meta 数据偏差/代表性方法学支撑）:contentReference[oaicite:83]{index=83}  

---

如果你希望我把上面每篇都补成“可直接粘贴进综述”的 APA 引用格式（并把缺失作者信息的条目从原文页首抓全），我可以在下一轮按“必读清单”逐篇补齐，并把“τ(L)/临界性/扩散参数”能直接复用的图表编号也一起摘出来。
