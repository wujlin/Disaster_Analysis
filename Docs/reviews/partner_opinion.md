我的结论很明确：这篇稿子有冲击 PNAS 的潜力，但我不建议以当前版本直接提交。选题本身很强，跨灾种、跨国家的数据框架也有明显的跨学科吸引力，主线问题也足够大，确实具备 PNAS 喜欢的“广泛科学读者可理解、且跨领域有意义”的气质。问题出在现稿还存在几处会被编辑和审稿人立刻抓住的硬伤，尤其是主文与补充材料不同步、样本定义和统计结果前后冲突、机制表述超出了目前证据强度，以及 PNAS 格式要件尚未补齐。  ([美国国家科学院院刊][1])

如果我是审稿人，我会给出“有意思，但需要大修后再考虑”的判断。稿件最吸引人的地方有三点：第一，它把灾后人口恢复这个典型的经验问题，提升成一个可检验的空间动力学问题；第二，它把经验相关、PDE 机制验证、跨尺度分析放在同一篇文章里，叙事完整；第三，Figure 2 到 Figure 4 已经勾出了一个很像高水平综合期刊的故事框架。单看构思，这篇稿子比一般灾害研究期刊稿件更有“普适规律”取向。

但当前版本最大的风险，是版本控制已经失守。主文第 4 页写 screened cohort 是 18 个事件，同时又写 primary event-level α–δnear analyses 使用 16 个事件子集；结果部分却反复称 18-event primary event-level sample。摘要给出的核心结果是 ρ = −0.70, p = 0.003，Figure 2d 写成 ρ = −0.69, p = 0.001，补充材料 Table S2 又对应另一套 16 事件结果 ρ = −0.526, p = 0.036。更严重的是，补充材料标题仍然是“Displacement geometry and perturbation amplitude predict… across hazard types and development levels”，这和主文题目、主结论已经不一致；补充 Table S1 的事件列表与补充 Figure S1/S2/S4 的事件集合也不一致。这类不同步在 PNAS 级别会极大削弱可信度，因为审稿人会先怀疑你到底在报告哪一版分析。这个问题必须在投稿前彻底清零。 

第二个核心问题，是理论机制与操作化指标之间还有一层没有打通。文中机制讲的是 spatial gradient、spatial frequency 和扩散松弛，真正拿来做核心预测的量却是 50 km 内的平均有符号偏差 δnear。这个量当然可能有预测力，但它与“梯度陡峭度”并不等价。你现在的写法从“near-field mean deviation”很快滑到了“steeper gradients”。补充材料 S5 甚至显示中场区间 50 到 100 km 的相关更强，这反而提示真正贴近机制的量，可能是区间差分、径向斜率，或者高阶模式能量占比，而不是单纯的近场均值。建议你把理论变量和经验变量重新对齐，至少补做三个指标对比：δnear，本地径向斜率估计，以及 near-minus-mid 的梯度型指标。谁最强，谁最稳，再决定主文到底讲什么。 

第三个问题，是你目前把 δnear 写成唯一关键预测量，但补充材料其实提示 Dpeak 也很重要。Table S2 显示 αemp 与 Dpeak 在多种 decay-rate 定义下都有关联；Table S6 甚至显示控制若干国家层面变量和 δnear 后，Dpeak 与 αemp 的相关仍然接近 +0.60。与此同时，Table S7 没有给出“控制 Dpeak 之后 δnear 是否仍然稳健”的对应检验。这会让审稿人很自然地问：几何形状到底是主导因素，还是扰动幅度本身也在起关键作用？所以我强烈建议你把主问题从“single quantity predicts recovery”改成“两类峰值信息如何共同预测恢复”，然后在主文里直接做一个简洁的联合模型，例如 α ~ δnear + log Dpeak，并给出留一事件交叉验证结果。这样叙事会更诚实，证据也更完整。

第四个问题，是 PDE 机制验证目前带有一定“用结果校准结果”的味道。补充材料 S3.5 里，k 和 Ds 是通过网格搜索来优化 αpred 和 αemp 的排序一致性、Pearson 相关和 MAE 的，这意味着模型参数是根据目标结果调出来的。随后再用这套参数去说“扩散机制解释了排序”，说服力会打折。再加上经验数据用的是 L1 型的 D(t)，且从峰后 24 小时起拟合；PDE 部分用的是 L2 型的 E(t)，且从 1 小时开始拟合。这个验证更适合表述为“与扩散机制一致”，还不足以支撑“扩散机制被证实”。最好的修补方法，是做真正的 out-of-sample 检验：例如 leave-one-event-out，或者留出整场风暴和整国事件，再看 δnear 和 PDE 排序还能不能站住。

第五个问题，是你对 power law 的表述过满。主文和摘要多次使用 universal、universally follows、same power-law form holds 这类非常强的措辞，但补充 Figure S1 里有事件的 R² 很低，甚至出现 α < 0；Figure S5 也说明并非每个事件都更支持 power law。geo-unit 分析同样有选择性问题，因为方法部分先保留了 R² ≥ 0.5 的 unit，再在结果里强调 76% 的 unit 达到 R² ≥ 0.7，并据此说 power law 在细尺度“普遍存在”。这个表述很容易被挑出“选择后再证明”的逻辑漏洞。更稳妥的写法是：在保留样本内，早期峰后恢复常可被 power law 近似；同时补充一张“全样本 versus 保留样本”的对比图。 

第六个问题，是样本独立性还需要再交代。你已经说过会合并同一物理事件的多个 FBDM deployment，以避免 pseudo-replication，但主文和补充里仍然包含同一命名风暴在不同地点的多个样本，例如 Beryl 的 Jamaica、QR、Texas，以及 Yagi 的不同地区。审稿人很可能会问：这些能否视为独立事件？此外，同一国家也有重复样本。你至少要补一个 leave-one-storm-out 或 leave-one-country-out 的稳健性检验。只要这一步过了，主结论会稳很多。 

第七个问题，是当前稿件离“PNAS submission-ready”还有一段距离。按 PNAS 当前作者指南，标题应简短并能让广泛科学读者理解，摘要不超过 250 词且要让一般科学读者读懂主要贡献，Significance Statement 需要 50 到 120 词，文内参考文献按出现顺序编号，标准研究论文通常约 4000 词左右，同时材料、数据、协议、代码和脚本应尽可能提供以支持复现。你的题目长度和摘要长度大体是合格的，但当前 PDF 里没有 Significance Statement，文内还是 author-year 引文风格，作者和单位仍有占位符，Supplementary Table 还留着 “??”，Data availability 和 Code availability 也还是待补 DOI 或链接的状态。这些都说明稿件现在还未进入正式投稿状态。 ([美国国家科学院院刊][2])

如果你准备按 PNAS 标准来大修，我建议优先做四件事。第一，统一主文、补充材料、图注、统计数字和事件列表，确保每个 n、每个 ρ、每个 p 都只有一个版本。第二，把“几何形状”与“扰动幅度”放进同一个预测框架里，给出主效应、增量解释力和交叉验证。第三，把 PDE 结果降格为机制一致性证据，同时补做真正的 holdout 检验。第四，全面收缩措辞，把 universally、predicts、support a mechanism、reframe 这类强词改成更符合当前证据边界的表达。 

下面给你一些更具体的文字润色建议。摘要第一句建议更直接、更平实，少一点“框架性宣言”的语气。比如把 “yet no general framework predicts how quickly populations recover” 改成 “but there is still no general way to estimate how quickly affected populations return toward baseline.” 这样更像 PNAS 摘要常见的开场。把 “universally follows a power-law decay” 改成 “is well approximated by a power-law decay over the early post-peak recovery window in the retained cohort.” 把 “predicted by a single quantity measurable at peak time” 改成 “strongly associated with a single peak-time spatial summary.” 把 “Three independent lines of evidence support a spatial-diffusion mechanism” 改成 “Three complementary analyses are consistent with a spatial-diffusion mechanism.” 这几处改法会明显降低被批“过度声称”的概率。

引言目前文献回顾很扎实，但略微偏长，前两页里“为什么值得 PNAS 读者关注”的信息还可以再前置。建议在第一段末尾加一句更面向广泛读者的话，比如强调：峰值时刻的空间几何若能提前编码恢复时长，早期人道主义资源配置就有了一个通用、可操作的预测入口。这样引言的“普适性”和“可用性”会更清楚。

方法部分最需要增强的是“可复核性”。你应当明确写出：peak 如何定义，plateau 如何定义，monotonic segment 如何裁剪，event center 对每一类灾害如何给定，tile ratio 到 annulus ratio 到 D(t) 究竟是 mean of ratios 还是 ratio of sums，annulus 在 D(t) 中为何等权而不是按面积或人口加权。当前方法能让熟悉该领域的人大致理解，但对 PNAS 这种更广泛的审稿群体，还不够“可被独立实现”。

结果部分建议把每段开头都明确样本数，并用一句话解释为何样本数会变。现在 18、16、14 在文中切换过快，读者很容易迷失。Figure 3d 也建议改，因为同一横轴上并列 event-level 的 Spearman ρ 与 geo-unit model 的 β，严格说不可直接比较。更稳妥的做法是都改成标准化效应量，或者拆成两个小面板。

讨论部分已经有很好的边界意识，但还可以再进一步。当前 “These findings reframe post-disaster recovery as governed by the physics of spatial redistribution” 这句话太满，容易让社会科学、灾害治理方向的审稿人反感。更稳的写法是：结果表明，峰值时刻的空间位移几何包含了恢复速度的重要信息，并与扩散型松弛机制相一致；基础设施损伤、政策响应、社会网络和地理边界等因素很可能决定了偏离这一基线机制的部分。这样会更成熟。

图表也需要一次系统清理。Figure 1 里至少有 “Aggragated” 和 “Trajecory” 两处拼写问题；主文还保留了 “Supplementary Table ??” 这样的占位符；Figure 4d 的 caption 需要明确写成 “among retained geo-units”；补充材料标题和表格标题也必须与主文完全同版。对于 PNAS，这些小问题会被直接解读成稿件还在拼接阶段。 

最后，给你一版可直接使用的 PNAS Significance Statement 草稿，你可以据此再细修：

Disasters can displace large populations within hours, yet responders still lack general tools to estimate how long recovery will take. Using standardized mobility maps from multiple hazards and countries, we show that recovery speed is strongly related to the spatial pattern of displacement at peak disruption. A simple peak-time measure of whether people disperse outward or concentrate near the impact center predicts later return rates, and similar scaling appears across local areas. These findings connect post-disaster mobility to general principles of spatial relaxation and suggest that early mobility maps can help anticipate the duration of humanitarian support.

总之，我的判断是：这篇稿子值得朝 PNAS 方向打磨，但当前版本还不宜直接投。先做一次彻底大修，尤其把版本一致性、统计稳健性和措辞边界这三件事修好，竞争力会明显上升。下一步最值得做的是直接把摘要、Significance Statement、Results 前两节和补充材料整套重写成同一版本。

[1]: https://www.pnas.org/author-center?utm_source=chatgpt.com "Submit to PNAS – Author Benefits and Submission Guide"
[2]: https://www.pnas.org/author-center/submitting-your-manuscript?utm_source=chatgpt.com "Submitting Your Manuscript - PNAS Submission Guidelines"
