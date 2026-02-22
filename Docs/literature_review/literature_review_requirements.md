# 文献检索需求清单与 Prompt

> **项目**：Disaster Recovery Dynamics  
> **目标**：系统梳理相关高水平文献，为研究定位和创新点识别提供支撑  
> **检索时间范围**：重点 2023-2026，经典文献不限年份

---

## 1. 检索目标与策略

### 1.1 检索目的

| 目的层次 | 具体目标 | 期望产出 |
|----------|----------|----------|
| **可行性验证** | 确认同类数据/问题已有什么工作 | 避免重复，找到 gap |
| **方法论借鉴** | 统计物理方法在社会系统的应用 | 方法选择依据 |
| **理论支撑** | 非平衡动力学、临界性、扩散理论 | 理论框架来源 |
| **对比参照** | 其他灾难案例的定量研究 | 普适性验证的潜在数据源 |

### 1.2 检索策略

```
             ┌─────────────────────────────────────┐
             │         本研究的核心定位             │
             │  统计物理 × 灾难 × 人类流动性        │
             └───────────────┬─────────────────────┘
                             │
       ┌─────────────────────┼─────────────────────┐
       │                     │                     │
       ▼                     ▼                     ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  数据同类     │     │  方法同类     │     │  问题同类     │
│  Facebook    │     │  统计物理     │     │  灾难恢复     │
│  Mobility    │     │  复杂系统     │     │  城市韧性     │
└──────────────┘     └──────────────┘     └──────────────┘
```

---

## 2. 检索需求清单（按优先级排序）

### 🔴 最高优先级：决定研究可行性

#### 2.1 同类数据已有工作

**检索关键词组合：**

```
("Facebook disaster maps" OR "Meta mobility data" OR "Data for Good") 
AND (earthquake OR disaster OR crisis)
```

**目标期刊：** Nature, Science, PNAS, Nature Communications, Scientific Reports, EPJ Data Science

**重点关注：**
- 使用同一数据源的已发表工作
- 研究方法与分析框架
- 数据局限性的讨论
- 尚未回答的问题

**期望产出：** 5-10 篇核心文献，明确我们的创新空间

---

#### 2.2 2023土耳其地震已有研究

**检索关键词组合：**

```
("Turkey earthquake 2023" OR "Kahramanmaraş earthquake" OR "Türkiye earthquake")
AND (mobility OR displacement OR evacuation OR recovery OR migration)
```

**目标期刊：** Lancet 系列、Nature 系列、PNAS、Disasters、Int J Disaster Risk Reduction

**重点关注：**
- 已有的定量分析
- 使用的数据源和方法
- 关注的科学问题
- 遗留的研究空白

**期望产出：** 3-8 篇，了解这个事件的研究现状

---

#### 2.3 灾难恢复的 Scaling 研究

**检索关键词组合：**

```
("disaster recovery" OR "post-disaster" OR "crisis recovery")
AND ("scaling law" OR "power law" OR "dynamics" OR "temporal pattern")
```

**目标期刊：** PRL, PRE, PRX, Nature Physics, Nature Communications, PNAS

**重点关注：**
- 恢复过程是否有定量刻画
- 使用的数学模型
- 发现的 scaling 关系
- 普适性的讨论

**期望产出：** 5-10 篇，确认我们的核心问题是否已被回答

---

### 🟠 高优先级：理论支撑

#### 2.4 社会系统的非平衡动力学

**检索关键词组合：**

```
("social system" OR "human behavior" OR "collective behavior")
AND ("relaxation" OR "non-equilibrium" OR "quench" OR "recovery dynamics")
```

**目标期刊：** Physical Review X, Physical Review E, J Stat Mech, New J Phys

**重点关注：**
- 社会系统是否被当作物理系统处理过
- 使用的理论框架
- Order parameter 的定义方式
- 弛豫动力学的结果

---

#### 2.5 人类流动的反常扩散

**检索关键词组合：**

```
("human mobility" OR "population movement" OR "travel patterns")
AND ("anomalous diffusion" OR "Lévy flight" OR "random walk" OR "diffusion")
```

**目标期刊：** Nature, Nature Physics, PRL, PRE, PNAS

**重点关注：**
- MSD 的测量方法
- 正常 vs 反常扩散的判据
- 机制解释
- 灾难对扩散特征的影响（如有）

**经典必读：**
- Brockmann et al., Nature 2006 (The scaling laws of human travel)
- Gonzalez et al., Nature 2008 (Understanding individual human mobility patterns)
- Song et al., Science 2010 (Limits of predictability in human mobility)

---

#### 2.6 城市韧性与 Scaling

**检索关键词组合：**

```
("urban resilience" OR "city recovery" OR "urban system")
AND ("scaling" OR "universal" OR "power law" OR "allometric")
```

**目标期刊：** Nature, Science, PNAS, Physical Review X, Nature Communications

**重点关注：**
- 城市系统的 scaling laws
- 韧性的定量定义
- 恢复时间尺度的研究
- Bettencourt/West 等人的工作

---

### 🟡 中等优先级：方法论参考

#### 2.7 疏散动力学与相变

**检索关键词组合：**

```
("evacuation" OR "mass displacement" OR "population displacement")
AND ("phase transition" OR "critical" OR "collective" OR "dynamics")
```

**目标期刊：** PRE, PRL, J Stat Phys, Physica A

**重点关注：**
- 疏散是否被建模为相变
- 临界点的识别方法
- 集体行为的涌现

---

#### 2.8 网络渗流与基础设施韧性

**检索关键词组合：**

```
("infrastructure" OR "network resilience" OR "urban network")
AND ("percolation" OR "failure cascade" OR "critical threshold")
```

**目标期刊：** Nature Physics, PRE, Physical Review X, Network Science

**重点关注：**
- 渗流理论在真实系统的应用
- 临界阈值的测量
- Finite-size effects 的处理

---

#### 2.9 临界减速与预警信号

**检索关键词组合：**

```
("critical slowing down" OR "early warning" OR "tipping point")
AND ("social" OR "complex system" OR "ecological")
```

**目标期刊：** Nature, Science, PNAS, PRL, Ecology Letters

**重点关注：**
- Scheffer 等人的 early warning signals 理论
- 社会系统中的应用
- 关联长度/恢复时间作为前兆

---

### 🟢 经典理论参考（不限年份）

#### 2.10 物理学经典理论

| 主题 | 关键文献/作者 | 需要理解的核心 |
|------|--------------|----------------|
| **KPZ 普适类** | Kardar, Parisi, Zhang 1986; 近期综述 | 界面生长的普适性，动态临界指数 |
| **Stretched exponential** | Kohlrausch 弛豫；Phillips, Rep Prog Phys 1996 | 多时间尺度弛豫的物理机制 |
| **渗流相变** | Stauffer & Aharony 书籍；Cohen & Havlin 综述 | 临界指数、有限尺寸标度 |
| **反常扩散** | Metzler & Klafter, Phys Rep 2000 | CTRW、分数阶动力学 |
| **复杂网络** | Barabási & Albert 1999; Newman 综述 | 网络结构与动力学 |

---

## 3. 检索输出模板

请按以下格式整理每篇文献：

```markdown
### [文献编号] 标题

**基本信息：**
- 作者：
- 期刊：
- 年份：
- DOI/链接：

**核心内容：**
- 研究问题：
- 使用数据：
- 核心方法：
- 主要发现：

**与本研究关系：**
- 可借鉴：
- 差异点：
- 我们的潜在创新：

**关键图/表：**
- （如有特别重要的结果图，标注 Figure 编号）

**引用价值：** ⭐⭐⭐⭐⭐ / ⭐⭐⭐⭐ / ⭐⭐⭐
```

---

## 4. AI 辅助文献检索 Prompt

### 4.1 通用检索 Prompt

```
You are an expert research assistant specializing in statistical physics, complex systems, and disaster science. I need you to help me conduct a systematic literature review.

**Research Context:**
- We are studying disaster recovery dynamics from a statistical physics perspective
- Data source: Facebook Disaster Maps (Turkey 2023 earthquake)
- Core question: Are there universal scaling laws in social system recovery?
- Methods: relaxation dynamics, anomalous diffusion, phase transitions, spatial correlations

**Search Task:**
[在此插入具体检索任务，例如：]
Find the most relevant papers published between 2023-2026 on using Facebook/Meta mobility data for disaster research.

**Output Requirements:**
For each paper, provide:
1. Full citation (APA format)
2. Core research question (1 sentence)
3. Key methodology (1-2 sentences)
4. Main findings (2-3 sentences)
5. Relevance to our work (1-2 sentences)
6. Potential gap we could address (if any)

Rank papers by relevance and impact. Focus on high-impact journals (Nature, Science, PNAS, PRL, PRX, Nature Communications, etc.)
```

### 4.2 特定主题检索 Prompt

#### Prompt A: 数据同类

```
Search for academic papers that:
1. Use Facebook Disaster Maps, Meta Data for Good, or similar mobile phone location data
2. Study disaster response, evacuation, or recovery
3. Published in 2023-2026
4. Published in high-impact journals

Specifically looking for:
- What analytical methods were used?
- What scientific questions were addressed?
- What were the main limitations acknowledged?
- What questions remain unanswered?

Output a ranked list of the 10 most relevant papers with detailed summaries.
```

#### Prompt B: 方法同类

```
Search for academic papers that apply statistical physics methods to social systems, specifically:

1. Relaxation dynamics in social/economic systems after perturbation
2. Phase transitions or critical phenomena in human collective behavior
3. Anomalous diffusion in human mobility
4. Scaling laws in urban systems

Time range: 2020-2026 for recent work, plus seminal classic papers

For each paper, explain:
- The physical framework used
- How order parameters or relevant quantities were defined
- What universal behaviors (if any) were found
- Methodological innovations

Focus on bridging papers that successfully translate physics concepts to social science.
```

#### Prompt C: 问题同类

```
I'm researching disaster recovery dynamics. Find papers that study:

1. Temporal patterns of recovery after natural disasters
2. Mathematical models of post-disaster population dynamics
3. Quantitative measures of urban/community resilience
4. Comparison of recovery across different disasters

Key questions to address:
- Has anyone characterized recovery using power laws or exponential decay?
- Are there known universal patterns in recovery across different disasters?
- What determines recovery timescales?

Prioritize empirical studies with quantitative analysis over purely qualitative work.
```

### 4.3 Gap 识别 Prompt

```
Based on the following research context, help me identify unexplored research gaps:

**Our Research:**
- Using Facebook Disaster Maps data from Turkey 2023 earthquake
- Applying statistical physics framework (relaxation, diffusion, phase transitions)
- Looking for universal scaling laws in social system recovery

**Known Literature (summarize what you found):**
[在此插入已检索到的文献摘要]

**Question:**
1. What specific aspects of disaster recovery dynamics remain unexplored?
2. Has statistical physics been systematically applied to this problem before?
3. What would constitute a novel contribution?
4. What are the potential challenges and how might they be addressed?

Be specific and cite relevant gaps in the existing literature.
```

---

## 5. 检索执行建议

### 5.1 检索工具

| 工具 | 用途 | 备注 |
|------|------|------|
| **Google Scholar** | 广泛检索 | 注意筛选高影响力期刊 |
| **Web of Science** | 精确检索 + 引用分析 | 需机构账号 |
| **Semantic Scholar** | AI 辅助相关性排序 | 免费，有 API |
| **Connected Papers** | 文献关系图谱 | 发现关联工作 |
| **arXiv** | 预印本 | 最新尚未发表的工作 |

### 5.2 检索流程

```
Step 1: 广泛搜索（每个主题）
    ↓
Step 2: 按影响因子/引用量筛选 Top 20
    ↓
Step 3: 阅读摘要，筛选 Top 10
    ↓
Step 4: 详细阅读，按模板记录
    ↓
Step 5: 绘制文献关系图谱
    ↓
Step 6: 识别 Research Gap
    ↓
Step 7: 汇总报告
```

### 5.3 时间预算建议

| 检索类别 | 预计时间 | 优先级 |
|----------|----------|--------|
| 同类数据 (2.1-2.3) | 4-6 小时 | 🔴 最高 |
| 理论支撑 (2.4-2.6) | 4-6 小时 | 🟠 高 |
| 方法论 (2.7-2.9) | 3-4 小时 | 🟡 中 |
| 经典理论 (2.10) | 2-3 小时 | 🟢 基础 |
| 汇总与 Gap 分析 | 2-3 小时 | 🔴 最高 |

---

## 6. 预期产出

### 6.1 文献清单

- **核心文献**（必读）：15-20 篇
- **重要参考**：20-30 篇
- **背景知识**：10-15 篇

### 6.2 综述报告

一份 3-5 页的报告，包含：

1. **研究现状总结**：该领域已知什么？
2. **方法论综述**：常用方法及其优缺点
3. **Gap 分析**：明确我们的创新空间
4. **定位建议**：我们的工作应如何定位
5. **参考文献列表**：分类整理

### 6.3 文献关系图

一张可视化图谱，展示：
- 核心文献之间的引用关系
- 主题聚类
- 我们工作的潜在定位

---

## 7. 检索结果反馈

完成检索后，请回答以下问题：

1. **是否存在直接竞争工作？**
   - 有没有人用同类数据做过类似分析？
   - 有没有人从统计物理角度研究过灾难恢复？

2. **创新空间在哪里？**
   - 数据层面的创新？
   - 方法层面的创新？
   - 问题层面的创新？

3. **潜在的合作/对比机会？**
   - 有没有可以合作的研究组？
   - 有没有可以对比的其他灾难数据？

4. **最需要关注的理论工作？**
   - 哪些理论框架最适合我们的问题？
   - 有没有现成的模型可以借用/改进？

---

*文档版本：v1.0*  
*创建日期：2026-01-29*  
*最后更新：2026-01-29*
