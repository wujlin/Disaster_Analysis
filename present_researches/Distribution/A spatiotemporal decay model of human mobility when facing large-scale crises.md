# A spatiotemporal decay model of human mobility when facing large-scale crises

Weiyu Li $^{a}$ , Qi Wang $^{b,1}$ , Yuanyuan Liu $^{c}$ , Mario L. Small $^{d}$ , and Jianxi Gao $^{e,1}$ 

Edited by Douglas Massey, Princeton University, Princeton, NJ; received February 18, 2022; accepted June 15, 2022 

A common feature of large-scale extreme events, such as pandemics, wildfires, and major storms is that, despite their differences in etiology and duration, they significantly change routine human movement patterns. Such changes, which can be major or minor in size and duration and which differ across contexts, affect both the consequences of the events and the ability of governments to mount effective responses. Based on naturally tracked, anonymized mobility behavior from over 90 million people in the United States, we document these mobility differences in space and over time in six large-scale crises, including wildfires, major tropical storms, winter freeze and pandemics. We introduce a model that effectively captures the high-dimensional heterogeneity in human mobility changes following large-scale extreme events. Across five different metrics and regardless of spatial resolution, the changes in human mobility behavior exhibit a consistent hyperbolic decline, a pattern we characterize as "spatiotemporal decay." When applied to the case of COVID-19, our model also uncovers significant disparities in mobility changes—individuals from wealthy areas not only reduce their mobility at higher rates at the start of the pandemic but also maintain the change longer. Residents from lower-income regions show a faster and greater hyperbolic decay, which we suggest may help account for different COVID-19 rates. Our model represents a powerful tool to understand and forecast mobility patterns post emergency, and thus to help produce more effective responses. 

spatiotemporal decay | commitment hyperbolic model | human mobility | extreme events | social disparities 

A considerable amount of research has examined human mobility. The latter has been shown to possess several fundamental and nearly universal patterns, such as high uniformity (1, 2), ultraslow diffusion (3-8), periodicity (9, 10), high predictability (11, 12), and motif composition (13, 14). However, large-scale, extreme events, such as hurricanes, wild fires, and pandemics can disrupt these patterns (15-19). Mobility perturbation, the deviation of human movements from their normal states, can be observed in the reduction of daily travel distances, changes in regular routes, and even evacuations to temporary locations. Many such changes impose major financial, medical, and quality of life costs (20-23), and as a result, mobility patterns often eventually return to some version of their prior states. However, the nature, extent, and duration of such changes vary widely from event to event (SI Appendix, Fig. S70), in large part because the events themselves differ so greatly. Wildfires and pandemics both alter human movement patterns, but they do so for different reasons, in different ways, and for different time periods. In addition, the heterogeneity of mobility change can vary at different geographies, manifested due to economy, demography, and physical and social infrastructure (SI Appendix, Fig. S71). This heterogeneity would suggest different responses with little connection across contexts. 

We report a model that effectively captures the underlying spatiotemporal pattern across what otherwise appear to be heterogeneous changes in mobility following different crises. Our model allows us to uncover the underlying uniformity across those differences by incorporating heterogeneity across space and over time in the perturbations caused by extreme events. We term the observed pattern the rate of spatiotemporal in mobility change. Our model reveals the existence of strong regularities in the degree of change in mobility behavior following extreme events and in the velocity of the return to normal, which provides the ability to predict complex human behaviors during large-scale crises and capture the hidden disparity between classes. We test the model against five metrics with datasets on human mobility across multiple large-scale events. In addition, we apply the model specifically to COVID-19 and show that it also unearths deep disparities across economic groups in movement behavior. 

# Results

A Model for Complex Mobility Behavior. We first introduce the model. Fig. 1 summarizes the assumptions behind our model, which aims to describe human mobility when 

# Significance

Following large-scale extreme events—such as hurricanes, wildfires, and pandemics—changes in human movement patterns can vary dramatically from place to place and in the weeks and months following the event. Identifying patterns in spite of such variations across space and over time can help societies mount more effective responses. Our model uncovers that, across multiple types of events and despite their diversity and complexity, such changes follow a predictable hyperbolic pattern. The model can help understand and forecast movement patterns in future extreme events. It also uncovers hidden disparities in behavioral changes due to income inequality post large-scale crises. 

Author affiliations: aSchool of Mathematical Sciences, Suzhou University of Science and Technology, Suzhou 215009, China; bDepartment of Civil and Environmental Engineering, Northeastern University, Boston, MA 02115; cLally School of Management, Rensselaer Polytechnic Institute, Troy, NY 12180; dDepartment of Sociology, Columbia University, New York, NY 10027; and eDepartment of Computer Science and NEST Center, Rensselaer Polytechnic Institute, Troy, NY 12180 

Author contributions: W.L., Q.W., Y.L., and J.G. designed research; W.L., Q.W., Y.L., M.L.S., and J.G. performed research; W.L. and Q.W. analyzed data; and M.L.S. and J.G. were the lead writers of the paper. 

The authors declare no competing interest. 

This article is a PNAS Direct Submission. 

Copyright © 2022 the Author(s). Published by PNAS. This article is distributed under Creative Commons Attribution-NonCommercial-NoDerivatives License 4.0 (CC BY-NC-ND). 

To whom correspondence may be addressed. Email: gaoj8@rpi.edu or jianxi.gao@gmail.com or q.wang@ northeastern.edu. 

This article contains supporting information online at http://www.pnas.org/lookup/suppl/doi:10.1073/pnas.2203042119/-DCSupplemental. 

Published August 8, 2022. 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-02-05/3ee608ea-786f-4d56-acee-7863343c4db7/a9729fd2c24dde1977a42391f1677d06e47c4ee2e14c34b27102f5c0b3abfb97.jpg)



Fig. 1. Spatiotemporal decay in mobility behavior during a large-scale crisis. (A) Mobility behaviors at the beginning of a crisis. Individuals across the country are likely to reduce their mobility but to different degrees. The individuals who live close to the nucleus of the crisis (dark red region) limit their mobility significantly while people who live far away (light red) reduce by a smaller degree. The severity of a crisis is measured differently in different crises. In health epidemics or pandemics, the number of infections is used to capture severity; in hurricanes, the amount of precipitation; in winter freeze, the temperature drop; etc. (B) The recovery of mobility behaviors. Although the pattern observed in (A) still holds, people's behaviors are assumed to ultimately begin to recover. The phenomenon of spatiotemporal decay is the key focus the model. The hypothesized decay patterns manifest in both spatial dimension (C) and temporal dimension (D).


perturbed by a large-scale crisis such as an epidemic, a tropical storm, or a wild fire. Immediately after the crisis occurs ( $T_0$ in Fig. 1A), individuals affected reduce their mobility but to different degrees. Individuals who live close to the nucleus of the crisis (i.e., the epicenter during COVID-19, the landfall location of a hurricane, the origin of a wildfire, etc.) (dark red region in Fig. 1A) are likely to limit their mobility substantially. Those living farther from the nucleus (light red regions in Fig. 1A), in contrast, change the mobility by a smaller degree, represented by the larger radius of movement. Such a pattern, termed spatial decay in this study, follows some version of the process represented abstractly in Fig. 1C. Over time, the mobility change starts to retreat, driven by the need and desire to return to normalcy. Therefore, in the later stages (i.e., $T_1$ ), the model assumes that people in every geography recover their mobility (Fig. 1B). Note that in Fig. 1 A-C, the severity of the crisis does not change. In reality, over time the severity can either attenuate (e.g., the weakening of a hurricane) or aggravate (e.g., more infection cases during a pandemic), complicating the reaction. To capture this complexity, we hypothesize that a similar decay function governs the temporal decay (Fig. 1D). 

On this basis, we develop a hyperbolic model that accounts for the spatiotemporal decay in mobility changes. We first define a hyperbolic model of a decay function: 

$$
r _ {i} (t) = \frac {r _ {i} (t)}{1 + k (t) \sum_ {j = 1} ^ {L} w _ {i j} N _ {j} (t)}. \tag {1}
$$

In Eq. 1, $w_{ij}N_j^i (t)$ captures spatial decay, where $w_{ij}$ is the spatial weight between location $i$ and location $j$ , and $N_j^i (t)$ is the 

severity of a crisis (e.g., precipitation, infection cases, etc.) in $j$ at time $t$ . For simplicity, we denote it as $WN(t)$ . $k(t)$ measures temporal decay; over time, the initial changes in mobility behaviors gradually diminish and disappear eventually. Therefore, $k(t)$ is a time-dependent dynamic function. 

We consider two decay functions for $k(t)$ (see SI Appendix, Fig. S1 for more details) and find that the exponential decay function describes the spatiotemporal decay processes we observe most accurately: 

$$
k (t) = k _ {0} e ^ {- \alpha t}. \tag {2}
$$

Here, $\alpha$ is the parameter that controls the decay. $K(0)$ is the initial rate of change in mobility behaviors, which we assume to be maximum at $t = 0$ . When $t$ is large enough, $k(t)$ approaches 0. 

Unifying Complex Mobility Behaviors. We test our model based on five different indicators of human movement. The metrics are time spent at home $(R_{1})$ , workers laboring in-person, which includes both full-time and part-time jobs $(R_{2})$ , intramobility flows within a county $(R_{3})$ , outward mobility flows on the county level $(R_{4})$ , and inward mobility flows on the county level $(R_{5})$ . Although the last three measures are related, they capture different phenomena. Consider a network in which counties are nodes and the visits are edges. $R_{3}$ is the weight of the self-loops in the networks or the alertness and safety of the county. $R_{4}$ captures self-initiated travels in which individuals voluntarily expose themselves to risks. $R_{5}$ describes received mobility and the associated risk involuntarily added to a county. See SI Appendix for details on the collection and explanation of these and other variables. 

We fit our model to several extreme events, involving a pandemic, a tropical storm, a hurricane, a winter freeze, and two wildfires. The mobility data for these events is provided by Safe-Graph (see Materials and Methods). We also test our model on two additional data sets to assess the generality of our model against different data sources (see SI Appendix, section 10). The starting point in our data is the start date of the high-impact crisis. For COVID-19, the start date is the date of emergency declaration from each state run from February 29, 2020 to March 16, 2020. For 2019 Tropical Storm Imelda, Hurricane Dorian, and the 2021 Winter Freeze, it is the landfall day. For the Saddleridge and Kincade wildfires, it is the day it spread to local communities; we used the concentration of PM2.5 in local communities to describe the severity of the impact of the wildfire. The results based on the presence of the wildfire or not (i.e., a binary measure) can be found in SI Appendix, sections 8 and 9. We first examined spatial decay by setting $k(t)$ to a constant (see Materials and Methods for details). Differences in perception lead to different levels of changes in mobility behaviors. For COVID-19, the dynamics of outward mobility flows on the county level ( $R_{4}$ ) (Fig. 2A, red lines) reveal a consistent pattern across different regions and crises. For example, outward mobility flows reduced 

drastically right after the emergency declarations and then slowly recovered (Fig. 2A). However, for the other crises, the mobility changes are less homogeneous (Fig. 2 B-D, red lines), most likely due to more diverse mobility changes in a short period of time. Take Tropical Storm Imelda as an example: while most people changed their mobility by reducing their travel, a portion of the population was forced to evacuate and seeks shelters. However, the predicted results from our model (blue lines in Fig. 2 A-D) align with the empirical data (red lines in Fig. 2 A-D). We observed essentially identical patterns across all $R_{i}$ . The results at the county level can be found in SI Appendix, Figs. S4 and S5. The predictability highlights the fundamental nature of spatial decay in people's social distancing behaviors. 

The patterns observed in Fig. 2 in our mobility metrics also make it clear that the temporal changes are dynamic, not constant. Thus, for the next analysis, we add $k(t)$ and transform the behavioral metrics $\frac{r_i(t)}{r_i(0)}$ by our model. Here, $r_i(t)$ is the value of $R_i$ at time $t$ , and $r_i(0)$ is the value before the large-scale crisis. As we show in Fig. 3, the metrics have a consistently inverse relationship with the spatiotemporal decay captured by $1 + k(t)WN(t)$ (see Fig. 3 A-T). The empirical results (red lines in Fig. 3 A-T) are predicted well by our models (blue lines). 


A


![image](https://cdn-mineru.openxlab.org.cn/result/2026-02-05/3ee608ea-786f-4d56-acee-7863343c4db7/2a4ddfc5d71bdf0349422ab35bc4f7defd55705981463dd1198f06cbcbcf6daf.jpg)



Fig. 2. Change in human mobility behavior after start of the crisis. (A) Changes in outward mobility flows $(R_d)$ over time during COVID-19. Red lines indicate data; blue lines, indicate results from the model. The flow decreased drastically at the beginning of COVID-19 and then slowly recovered. We observed similar temporal patterns for four other COVID-19 metrics (see SI Appendix, Figs. S2-S5). Changes in outward mobility flows with time during 2019 Tropical Storm Imelda and 2019 Hurricane Dorian (B), the extreme events of 2019 Saddleridge and Kincade Wild Fires (C), and the 2021 Texas Winter Freeze (D).


![image](https://cdn-mineru.openxlab.org.cn/result/2026-02-05/3ee608ea-786f-4d56-acee-7863343c4db7/6f26011daf6f209ee8fb67e2bcaefa1f248ffd53b957f4dd9aa6575e43ca654b.jpg)



Fig. 3. Mobility metrics transformed by our unified model. $r_i(t)$ is the value of $R_i$ at time $t$ , $r_k(0)$ is the value before the pandemic, $k(t)$ is the decay function of social discounting behaviors, and $WN(t)$ is the numbers of infections cases at $t$ (see SI Appendix for details). Dots represent data from the counties of the states and regions in the United States, the blue lines represent results from our theoretical model. We observe high consistency as the changes in social distancing behaviors follow $r_i(t) / r_i \propto 1/(1 + k(t)WN)$ with high $R^2$ . In (A)-(E), different colors of the dots represent different states in the United States. In (F)-(T), color represents different large-scale crises.


The results demonstrate that our model accounts for complex behavioral changes under a simple governing equation (Eq. 1). During COVID-19, mobility metrics from each county (dots in Fig. 3 $A-E$ ) in each state (different colors in Fig. 3 $A-E$ ) are tightly distributed around our prediction (blue lines). Similarly, our model (blue lines in Fig. 3 $F-T$ ) can predict mobility changes in counties across extreme events (colored dots in Fig. 3 $F-T$ ). The striking uniformity hidden in mobility behavior makes it possible to predict future changes. 

Using the Model to Understand Disparities. The spatiotemporal decay model does not only predict human mobility changes after public crises; it also provides a tool to explore hidden patterns in mobility changes across different population groups. Particularly, two of the model's key metrics, the initial reduction in mobility $(k_{0})$ and rate of temporal decay $(\alpha)$ , can be used to compare the magnitude and perseverance of mobility changes following 

adversity. Here, we demonstrate the value of the metrics for understanding COVID-19 and disparities among populations from different income groups. 

We classify counties into 10 classes of equal frequency based on per capita income; each class includes 305 counties. We find positive relationships between income and $k_{0}$ among all five metrics (Fig. 4A), suggesting that populations from higher-income counties are more likely to have a substantial reduction in their mobility. We also find a negative relationship between income and $\alpha$ (Fig. 4B), indicating that people from lower-income counties returned to their prior behavior faster. 

The faster temporal decay in populations from low-income communities places them at a higher risk of exposure to the deadly virus. We classify the weighted cumulative confirmed cases $WN(t)$ and the logarithmic decay rate $\ln k(t)$ into 10 classes, respectively, and then calculate the conditional probabilities $P\{WN(t) \mid k(t - l)\}$ and $P\{k(t - l) \mid WN(t)\}$ as follows: 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-02-05/3ee608ea-786f-4d56-acee-7863343c4db7/ba2a03c86d4e9274bdc2b5d170a6e132ddbf7491cec1d5f50aeeb8b0f646896b.jpg)


![image](https://cdn-mineru.openxlab.org.cn/result/2026-02-05/3ee608ea-786f-4d56-acee-7863343c4db7/d6c99a5e81550ed483c70b33c6526d2db61f0c9bbb6361ef546e67304f9adcb7.jpg)



Fig. 4. Mobility behavior differs among class groups. (A) The relationship between income and social distancing behaviors $(k(0))$ at the beginning of the pandemic. We break the 3,050 counties into 10 equal groups based on the income per capita (see SI Appendix, Fig. S6). The increase in income leads to a higher level of social distancing. (B) The relationship between income and the decay $(\alpha)$ of social distancing behaviors. The increase in income leads to a slower decay, meaning people from high-income communities can stay at home longer or afford to delay in returning to work. In contrast, people from low-income neighborhoods are forced to return to their pre-pandemic behaviors faster.


$$
\begin{array}{l} P \left\{W N (t) = C _ {i} \mid k (t - l) = C _ {j} \right\} \\ = \frac {P \left\{W N (t) = C _ {i} , k (t - l) = C _ {j} \right\}}{P \left\{k (t - l) = C _ {j} \right\}}, \tag {3} \\ \end{array}
$$

$$
\begin{array}{l} P \left\{k (t) = C _ {i} \mid W N (t - l) = C _ {j} \right\} \\ = \frac {P \left\{k (t) = C _ {i} , W N (t - l) = C _ {j} \right\}}{P \left\{W N (t - l) = C _ {j} \right\}}, \tag {4} \\ \end{array}
$$

where $l$ is the time lag, and $C_i$ is the class. We use $C_1$ to denote the class with the lowest values, $C_{10}$ the highest values, and set $l = 5$ d to calculate the conditional probabilities. Fig. 5A shows the conditional probability of weighted infection cases $WN(t - l)$ in causing the changes in $k(t)$ for all populations, and Fig. 5 B and $C$ for the poorest and most wealthy populations, respectively. We use the same trend line of the highest probabilities of the 10 classes obtained from Fig. 5A as a baseline for benchmarking purposes in both Fig. 5 B and C. The conditional probability is substantially below the baseline in the poorest communities and above it in the wealthiest neighborhoods. The results show that the increases in infection cases have a higher probability of causing mobility reduction in high-income neighborhoods than in low-income neighborhoods. This finding suggests that people from the latter are less likely to have the means or resources to commit to social distancing during the pandemic. 

# Discussion

Our findings draw from extensive sample data and are robust to several dimensions of human mobility behavior in multiple resolutions (i.e., county, state, and country levels) across multiple types of large-scale crises. We note that our study shares limitations with other studies using similar data (24-27): the data only cover a portion of the population and with incomplete demographic information. Also, our dataset is on the census block group level, and thus is not informative about patterns among smaller geographical units. 

In addition, our model has important limitations. Notably, it may not perform well against crises with waves of worsening and relief, where movement patterns may proceed more erratically over the long run. Long-term stresses caused by these types of crises can alter psychological and social conditions and thus human responses. In addition, our model focuses on geographical distances without considering social networks. Mobility during crises can also be driven by social connections, which operate 

differently in different contexts and may undermine our model's predictive power in regions with social dynamics different from those in the United States. Future studies should incorporate these elements into the models. 

Still, our analyses suggest a few important conclusions. First, the changes in mobility after large-scale crises are consistently hyperbolic across space and over time. The surprising uniformity reveals that spatiotemporal decay governs how people react to large-scale crises. It is notable that while prior research has discovered some consistent properties in human mobility (12, 28-31), our study, to the best of our knowledge, is the first to report an apparently fundamental pattern following severe perturbations caused by extreme events. The model could serve as a powerful tool to predict human behaviors on different scales. As governments assess and develop effective measures and policies to cope with an increasing number of natural and human-made crises, models such as ours will be necessary (29, 32, 33). 

The model provides key metrics for mobility analyses post large-scale crises: $k_{i}$ to understand the level of mobility changes, and $\alpha$ represents the speed to return normalcy. We use COVID-19 to demonstrate their powers to quantitatively measure these values. The result reveals the disparity in the practice and maintenance of mobility changes during COVID-19. Therefore, this study adds another dimension to the evidence (24, 34) that income inequality plays a damaging role in the consequences of the pandemic, here through the mechanism of degree and duration of the commitment to limiting one's mobility (i.e., social distancing). Inequality can plague disadvantaged communities in unusual ways during large-scale public crises such as COVID-19, and our model provides a tool to examine one set of mechanisms accounting for how. 

Last, it is worth noting that our spatial weighting mechanism is highly malleable and thus can be used to capture different types of movement patterns. As we demonstrated above (see SI Appendix, section 2.2), $w_{ij}N_j(t)$ is able to convert the mobility variables $R_{1}$ to $R_{5}$ on both the county and state levels across the 50 states. As shown in Figs. 2 and 3, our model can predict seemingly chaotic changes in mobility behavior after short-term abrupt after natural disasters. 

# Materials and Methods

Datasets. We use data provided by SafeGraph, a company that generates human mobility data sets using a panel of GPS pings from anonymous mobile 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-02-05/3ee608ea-786f-4d56-acee-7863343c4db7/681929cdbbac42cf6b5cba284c47ecd38183b03abf0fc8d1c5ee68c97af52cb9.jpg)


![image](https://cdn-mineru.openxlab.org.cn/result/2026-02-05/3ee608ea-786f-4d56-acee-7863343c4db7/a174b1ef777e9c4a7722b703d22460ff571217d4578bb5fe586fe8050a2c81e6.jpg)


![image](https://cdn-mineru.openxlab.org.cn/result/2026-02-05/3ee608ea-786f-4d56-acee-7863343c4db7/4dec62dd4be253d30bebbe65f626c8376d85f70324647228d1a4471cc3e59737.jpg)



Fig. 5. The conditional probabilities between social distancing behaviors and the cumulative confirmed cases. (A) The conditional probabilities $P(k|cases)$ of social distancing behaviors $k(t)$ given the class of cumulative confirmed cases five days prior for all counties. The line is the linear trend line of the highest probabilities of the 10 classes of the cases. We use it in both (B) and (C) for benchmarking purposes. (B) $P(k|cases)$ for low-income counties (i.e., bottom 10%). (C) $P(k|cases)$ for high-income counties (i.e., top 10%). The comparison between (B) and (C) shows that only in high-income communities a higher number of cumulative cases are likely to lead to a higher level of social distancing behaviors $k$ .


devices. The data set reports key measures related to people's mobility behaviors on the census block group (CBG) level. We studied the following events: 

2019 Hurricane Dorian: August 28, 2019-September 2, 2019; 

2019 Tropical Storm Imelda: September 17, 2019-September 21, 2019; 

2019 Saddleridge Wildfire: October 10, 2019-October 31, 2019; 

2019 Kincade Wildfire: October 23, 2019-November 6, 2019; 

COVID-19: February 1 2020-May 2020; and 

2021 Texas Winter Freeze: February 10, 2021-February 20, 2021. 

In our study, five variables are used as $r$ . These variables have positive $ks$ for the majority of counties, and thus their values have reduced during extreme events. According to SafeGraph, a user's home is the common nighttime (6 PM-7 AM) location for the device over a 6-wk period. The number of devices from on CBG is the users whose homes are in this same CBG. As for the work behavior devices, we sum the numbers of part-time works with the full-time workers from the data set. Therefore, the workers are the devices that spend greater than 3 h outside their home during 8 AM-6 PM. Last, the non-home dwell time per day is $24 \times 60$ minus the median dwell time at home in minutes. The data were aggregated to the county level for our analyses. 

Modified Mobility Model. We considered three functions to describe the commitment decay in human behaviors, including (1) the hyperbolic delay discounting function (RH) (35), (2) hyperbolic delay discounting equation (GM) (36), and (3) Exponential discounting function (ED) (37). In this study, we focus on the RH model (discussions on other models can be found in the SI Appendix): 

$$
v _ {i} = \frac {V _ {i}}{1 + k \left(\sum_ {j = 1} ^ {L} w _ {i j} N _ {j}\right) ^ {s}}, \tag {5}
$$



1. R. Jurdak et al., Understanding human mobility from Twitter. PLoS One 10, e0131469 (2015). 





2. D. Brockmann, L. Hufnagel, T. Geisel, The scaling laws of human travel. Nature 439, 462-465 (2006). 





3. J. L. Toole, C. Herrera-Yaqüe, C. M. Schneider, M. C. González, Coupling human mobility and social ties. J. R. Soc. Interface 12, 20141128 (2015). 





4. C. Song, Z. Qu, N. Blumm, A.-L. Barabasi, Limits of predictability in human mobility. Science 327, 1018-1021 (2010). 





5. C. Song, T. Koren, P. Wang, A.-L. Barabási, Modelling the scaling properties of human mobility. Nat. Phys. 6, 818 (2010). 





6. A. Noulas, S. Scellato, R. Lambiotte, M. Pontil, C. Mascolo, A tale of many cities: Universal patterns in human urban mobility. PLoS One 7, e37027 (2012). 





7. A. Cuttone, S. Lehmann, M. C. González, Understanding predictability and exploration in human mobility. EPJ Data Sci. 7, 1-17 (2018). 





8. X.-Y. Yan, C. Zhao, Y. Fan, Z. Di, W.-X. Wang, Universal predictability of mobility patterns in cities. J. R. Soc. Interface 11, 20140834 (2014). 





9. E. Cho, S. A. Myers, J. Leskovec, "Friendship and mobility: User movement in location-based social networks" in Proceedings of the 17th ACM SIGKDD International Conference on Knowledge Discovery and Data Mining (ACM, 2011), pp. 1082-1090. 10.1145/2020408.2020579. 





10. X. Liang, X. Zheng, W. Lv, T. Zhu, K. Xu, The scaling of human mobility by taxis is exponential. Physica A 391, 2135-2144 (2012). 





11. C. M. Schneider, V. Belik, T. Couronne, Z. Smoreda, M. C. González, Unravelling daily human mobility motifs. J. R. Soc. Interface 10, 20130246 (2013). 





12. J. P. Bagrow, D. Wang, A.-L. Barabási, Collective response of human populations to large-scale emergencies. PLoS One 6, e17680 (2011). 





13. C. M. Schneider, C. Rudloff, D. Bauer, M. C. González, "Daily travel behavior: Lessons from a week-long survey for the extraction of human mobility motifs related information" in Proceedings of the 2nd ACM SIGKDD International Workshop on Urban Computing (ACM, 2013), pp. 1-7. 



where $v_{i}$ is the decay rate of the mobility of region $i$ , $i = 1, 2, \dots, L$ , and $V_{i}$ is the corresponding denotes the regular mobility value. $N_{i}$ is the measure of hazard level. $W = (w_{ij})_{L \times L}$ is a weight matrix with $w_{ij}$ denoting the effect of region $j$ on region $i$ . There are two free parameters, $s$ and $k$ . Parameter $s$ determines the sensitivity to hazard which causes changes in mobility behavior and is set to 1 in this study. $k$ measures the degree of the decay of mobility change. A larger $k$ describes a higher level of alertness and thus sustaining of the change in mobility behavior. We also consider the decay process of reaction reduction, where $k$ is set as a time-dependent parameter. Finally, we get the model provided in Eq. 2. 

Comparison of Model Performance. The error of the model is evaluated by the symmetric mean absolute percentage error (SMAPE): 

$$
S M A P E = \frac {100 \%}{n} \sum_ {i = 1} ^ {n} \frac {\left| \hat {r} _ {i} - r _ {i} \right|}{\left(\left| \hat {r} _ {i} \right| + \left| r _ {i} \right|\right) / 2}. \tag{6}
$$

The SMAPE of different models for different variables can be found in SI Appendix, Fig. S2. The RH model with exponential decay is superior to other models in most cases. Therefore, we use the RH model with exponential decay (RHED, see Eqs. S7-S9). 

Data, Materials, and Software Availability. Data are private and protected by SafeGraph (https://docs.safegraph.com/docs/social-distancing-metrics). Python code used to process the data and generate the results is made publicly available on the author's GitHub page (https://github.com/he-h/Covid-Mobility-Network-Analysis). 

ACKNOWLEDGMENTS. We acknowledge the support of the US National Science Foundation (2047488, 2027744, and 2125326) and the Rensselaer-IBM AI Research Collaboration. 



14. J. Candia et al., Uncovering individual and collective human dynamics from mobile phone records. J. Phys. A Math. Theor. 41, 224015 (2008). 





15. T. Horanont, S. Phithakkitnukoon, T. W. Leong, Y. Sekimoto, R. Shibasaki, Weather effects on the patterns of people's everyday activities: A study using GPS traces of mobile phone users. PLoS One 8, e81153 (2013). 





16. L. Bengtsson, X. Lu, A. Thorson, R. Garfield, J. von Schreeb, Improved response to disasters and outbreaks by tracking population movements with mobile phone network data: A post-earthquake geospatial study in Haiti. *PLoS Med.* 8, e1001083 (2011). 





17. M. Serafino et al., Digital contact tracing and network theory to stop the spread of COVID-19 using big-data on human mobility geolocation. PLOS Comput. Biol. 18, e1009865 (2022). 





18. W. Wang, S. Yang, H. E. Stanley, J. Gao, Local floods induce large-scale abrupt failures of road networks. Nat. Commun. 10, 2114 (2019). 





19. H. Deng et al., High-resolution human mobility data reveal race and wealth disparities in disaster evacuation patterns. Humanit. Soc. Sci. Commun. 8, 144 (2021). 





20. S. K. Brooks et al., The psychological impact of quarantine and how to reduce it: Rapid review of the evidence. Lancet 395, 912-920 (2020). 





21. A Jawaid, Protecting older adults during social distancing. Science 368, 145 (2020). 





22. A. Venkatesh, S. Edirappuli, Social distancing in COVID-19: What are the mental health implications? BMJ 369, m1379 (2020). 





23. M. Carvalho Aguiar Melo, D. de Sousa Soares, Impact of social distancing on mental health during the COVID-19 pandemic: An urgent discussion. Int. J. Soc. Psychiatry 66, 625-626 (2020). 





24. S. Chang et al., Mobility network models of COVID-19 explain inequities and inform reopening. Nature 589, 82-87 (2021). 





25. N. J. S. Ashby, Impact of the COVID-19 pandemic on unhealthy eating in populations with obesity. Obesity (Silver Spring) 28, 1802-1805 (2020). 





26. Y. Kang et al., Multiscale dynamic human mobility flow dataset in the U.S. during the COVID-19 epidemic. Sci. Data 7, 390 (2020). 





27. J. A. Weill, M. Stigler, O. Deschenes, M. R. Springborn, Social distancing responses to COVID-19 emergency declarations strongly differentiated by income. Proc. Natl. Acad. Sci. U.S.A. 117, 19658-19660 (2020). 





28. M. C. González, C. A. Hidalgo, A.-L. Barabási, Understanding individual human mobility patterns. Nature 453, 779-782 (2008). 





29. L. Alessandretti, U. Aslak, S. Lehmann, The scales of human mobility. Nature 587, 402-407 (2020). 





30. M. Schläpfer et al., The universal visitation law of human mobility. Nature 593, 522-527 (2021). 





31. D. Wang et al., "Human mobility, social ties, and link prediction" in Proceedings of the 17th ACM SIGKDD International Conference on Knowledge Discovery and Data Mining (ACM, 2011), pp. 1100-1108. 





32. N. E. Phillips, B. L. Levy, R. J. Sampson, M. L. Small, R. Q. Wang, The social integration of American cities: Network measures of connectedness based on everyday mobility across neighborhoods. *Social. Methods Res.* 50, 004912411985238 (2019). 





33. J. Gao, Y. Yin, B. F. Jones, D. Wang, Quantifying policy responses to a global emergency: Insights from the COVID-19 pandemic (2020). https://papers.ssrn.com/abstract=3634820. 10.2139/ssrn.3634820. 





34. Q. Wang, N. E. Phillips, M. L. Small, R. J. Sampson, Urban mobility and neighborhood isolation in America's 50 largest cities. Proc. Natl. Acad. Sci. U.S.A. 115, 7735-7740 (2018). 





35. H. Rachlin, Notes on discounting. J. Exp. Anal. Behav. 85, 425-435 (2006). 





36. L. Green, J. Myerson, A discounting framework for choice with delayed and probabilistic rewards. Psychol. Bull. 130, 769-792 (2004). 





37. R. Grace, The matching law and amount-dependent exponential discounting as accounts of self-control choice. J. Exp. Anal. Behav. 71, 27-44 (1999). 

