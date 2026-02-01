# Phase Separation Summary (three-phase: + - +)
判定口径：对每个灾难，在若干时间点取最近的窗口，比较距离带的 $\phi_{agg}$ 相对 1 的符号（>1+eps 为 +，<1-eps 为 -）。
## turkiye_earthquake_2023  (earthquake)
- name: Turkiye Turkey Earthquake Full Country Version Feb 8 2023
- eps: 0.05
- three-phase exists: True

| t_req(h) | t_used(h) | three_phase | raw | collapsed |
|---:|---:|---:|---|---|
| 16 | 16 | 0 | `+---0` | `+-` |
| 40 | 40 | 0 | `+---0` | `+-` |
| 88 | 88 | 0 | `+-+-0` | `+-+-` |
| 160 | 160 | 1 | `+-+0+` | `+-+` |
| 832 | 832 | 0 | `+++++` | `+` |

## hurricane_beryl_pre_landfall_2024  (hurricane)
- name: Hurricane Beryl Pre Landfall Disaster Maps June 30 2024
- eps: 0.05
- three-phase exists: False

| t_req(h) | t_used(h) | three_phase | raw | collapsed |
|---:|---:|---:|---|---|
| 16 | 16 | 0 | `?+0--` | `+-` |
| 40 | 40 | 0 | `?00--` | `-` |
| 88 | 88 | 0 | `?00--` | `-` |
| 160 | 160 | 0 | `?0000` | `` |
| 832 | 736 | 0 | `?00--` | `-` |

## moldova_flooding_2024  (flood)
- name: Moldova Flooding Sept 16 2024
- eps: 0.05
- three-phase exists: False

| t_req(h) | t_used(h) | three_phase | raw | collapsed |
|---:|---:|---:|---|---|
| 16 | 16 | 0 | `0000?` | `` |
| 40 | 40 | 0 | `0000?` | `` |
| 88 | 88 | 0 | `0+00?` | `+` |
| 160 | 160 | 0 | `0+00?` | `+` |
| 832 | 640 | 0 | `0+00?` | `+` |

## park_fire_2024  (wildfire)
- name: The Park Fire in Northern California, US
- eps: 0.05
- three-phase exists: False

| t_req(h) | t_used(h) | three_phase | raw | collapsed |
|---:|---:|---:|---|---|
| 16 | 16 | 0 | `00000` | `` |
| 40 | 40 | 0 | `00000` | `` |
| 88 | 88 | 0 | `00000` | `` |
| 160 | 160 | 0 | `00000` | `` |
| 832 | 376 | 0 | `+0+++` | `+` |

