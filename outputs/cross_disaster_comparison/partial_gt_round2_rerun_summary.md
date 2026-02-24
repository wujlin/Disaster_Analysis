# Partial GT Round2 重跑汇总

- catalog_total_events: 42
- catalog_excluded_unresolved10: 10
- catalog_included_events: 32
- phi_heatmap_events: 32
- metadata_t0_provided_exact: 32
- metadata_center_provided: 32
- geo_timeseries_rows: 305448
- geo_fit_rows: 6336
- geo_events_with_timeseries: 32
- geo_events_with_fit: 24
- geo_events_without_fit: 8
- dt_event_summary_rows: 32
- dt_routeb_flag_rows: 17
- dt_routeb_selected_events: 9

- geo_out_dir: outputs/cross_disaster_comparison/geo_unit_scale_partial_gt_round2_included32_20260224_132836
- dt_out_dir: outputs/cross_disaster_comparison/Dt_decay_partial_gt_round2_included32_20260224_133240

## Geo 无拟合事件（n_units_fit=0）
- global_earthquake_model_research_2025_sep_18
- hurricane_john_across_southeastern_guerrero_mexico
- hurricane_melissa_10_27_2025
- hurricane_melissa_aftermath_2025_11_03
- mountain_fire_in_california
- the_earthquake_across_central_mexico
- the_earthquake_across_dhaka_division_bangladesh
- typhoon_nika_across_northern_luzon_philippines

## Dt RouteB 选中事件
- flooding_in_central_and_eastern_europe_sept_16_2024
- park_fire_california_29_july_2024
- spain_flood
- the_flooding_across_bagmati_and_koshi_provinces_nepal
- the_flooding_across_rio_grande_do_sul_state_brazil
- the_wildfires_in_quito_pichincha_province_ecuador
- tropical_storm_debby_united_states_pre_landfall_4_august_2024
- turkiye_earthquake_2023
- typhoon_yagi_across_northeastern_vietnam

## Mixed-effects
- delta_peak_unit: status=ok, coef=-0.0797772393124163, p=0.1051535394503092, n_obs=6336, n_events=24
- distance_km: status=ok, coef=2.0727256381026665e-05, p=0.0790571978421417, n_obs=6336, n_events=24
- D_peak_unit: status=ok, coef=0.3097036575735689, p=1.5237011566595787e-06, n_obs=6336, n_events=24