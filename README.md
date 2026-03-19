# Disaster Recovery Dynamics

This repository studies how population displacement relaxes after disasters, with a focus on whether post-disaster recovery exhibits reproducible scaling patterns and which spatial signatures are most informative about recovery speed. The project combines Facebook Disaster Maps–based measurements with cross-disaster comparison, mechanism-oriented modeling, and event-level as well as geo-unit–level analysis.

## Project scope

The repository is organized around three linked questions:

1. What functional form best describes post-peak recovery?
2. Which peak-time spatial features are associated with subsequent recovery speed?
3. Which mechanisms are consistent with the observed recovery patterns across disasters and spatial scales?

The current workflows include single-event diagnostics, cross-disaster comparison, robustness checks, and manuscript-facing figure generation.

## Data and analysis focus

- **Primary data source:** Facebook Disaster Maps / Data for Good products
- **Core measurements:** population redistribution, movement, network coverage, and related recovery indicators
- **Spatial units:** Bing-tile-based products, with many pipelines operating on Level 14 tiles and derived geo-units
- **Analysis modes:** event-level recovery, spatial-profile diagnostics, geo-unit heterogeneity, and mechanism validation

## Repository layout

```text
Disaster/
├── README.md                  # Project overview
├── Data/                      # Local raw data (gitignored)
├── Docs/                      # Project documentation, catalogs, methods, and experiment notes
├── src/disaster/              # Reusable library code
├── scripts/                   # Reproducible CLI entry points
├── analysis/                  # Legacy or exploratory entry points kept for compatibility
├── outputs/                   # Curated shareable run artifacts
├── Essay/                     # Local manuscript workspace (gitignored)
├── legacy/                    # Local archived assets and local-only outputs (gitignored)
└── config/                    # Local configuration and authentication material
```

## Key documentation

- `Docs/research_framework.md` — research framing and scientific questions
- `Docs/data_pipeline.md` — data flow and processing logic
- `Docs/Methods.md` — method notes, diagnostics, and design decisions
- `Docs/cross_disaster_catalog.md` — event catalog and cross-disaster bookkeeping
- `Docs/visual_style_guide.md` — project-facing figure style reference

## Environment setup

```bash
conda create -n disaster python=3.10
conda activate disaster
pip install -r requirements.txt
```

## Quick start

For the population-relaxation workflow:

```bash
# Smoke test
python scripts/population_relaxation.py --max-files 3

# Full run
python scripts/population_relaxation.py
```

Outputs are written to `outputs/population_relaxation/`.

For post-fit diagnostics:

```bash
python scripts/population_postfit_analysis.py
python scripts/beta_robustness.py
```

## Local-only material

The following content is intentionally kept out of version control:

- manuscript files under `Essay/`
- archived local workspace assets under `legacy/local_workspace/`
- archived local output folders under `legacy/local_outputs/`
- local secrets and downloaded datasets configured through `.gitignore`

This separation keeps the repository focused on reusable code, shareable outputs, and project documentation.
