# Reproduction Guide

End-to-end instructions for reproducing the AlphaMining benchmark experiments
(SP500 and CSI500/CSI300 universes) from a fresh machine.

---

## Table of contents

1. [Prerequisites](#1-prerequisites)
2. [Directory layout](#2-directory-layout)
3. [Clone the repos](#3-clone-the-repos)
4. [Set up conda environments](#4-set-up-conda-environments)
5. [Data pipeline — US (SP500)](#5-data-pipeline--us-sp500)
6. [Data pipeline — CN (CSI500 + CSI300)](#6-data-pipeline--cn-csi500--csi300)
7. [Build Docker images](#7-build-docker-images)
8. [Run the experiments](#8-run-the-experiments)
9. [Evaluate results](#9-evaluate-results)
10. [Output structure](#10-output-structure)
11. [Cost and time estimates](#11-cost-and-time-estimates)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Prerequisites

| Tool | Version | Notes |
|---|---|---|
| macOS or Linux | — | macOS Sequoia 15 / Ubuntu 22.04 tested |
| Docker Desktop | ≥ 24 | Must be running; Apple Silicon: enable "Use Rosetta" optional |
| Miniconda / Conda | ≥ 23 | Used to create `alphaagent` and `quantaalpha` envs for the data pipeline |
| Python (host) | 3.10–3.12 | Only needed to run the evaluator outside Docker |
| Git | ≥ 2.30 | — |
| ~60 GB free disk | — | Images (~5 GB each), Qlib data (~15 GB US + ~10 GB CN), results |

OpenAI-compatible API key (OpenAI, DeepSeek, or a self-hosted vLLM endpoint).

---

## 2. Directory layout

All repos must live **as siblings in the same parent directory**.
The `build.sh` scripts resolve paths relative to each other.

```
<parent>/
├── alphamining_benchmark/            ← the benchmark harness (this repo)
├── Alphamining_agent_benchmark_us/   ← US experiment repo
│   ├── AlphaAgent/                   ← AlphaAgent source (placed here — see §3)
│   ├── QuantaAlpha/                  ← QuantaAlpha source (placed here — see §3)
│   ├── DataPipeline/                 ← data-download scripts
│   └── qlib/                         ← Microsoft Qlib source (cloned here — see §3)
└── Alphamining_agent_benchmark_cn/   ← CN experiment repo (identical structure)
    ├── AlphaAgent/
    ├── QuantaAlpha/
    ├── DataPipeline/
    └── qlib/
```

> **Why two separate experiment repos?** AlphaAgent and QuantaAlpha use slightly
> different Qlib data directories on the CN side (CSI500 vs CSI300) and the
> `DataPipeline/` scripts resolve paths relative to the repo root. Keeping them
> separate avoids path collisions.

---

## 3. Clone the repos

```bash
mkdir -p ~/alphamining && cd ~/alphamining

# 1. Benchmark harness
git clone https://github.com/EricZhang12138/alphamining-benchmark alphamining_benchmark

# 2. US experiment repo
git clone <Alphamining_agent_benchmark_us_url> Alphamining_agent_benchmark_us

# 3. CN experiment repo
git clone <Alphamining_agent_benchmark_cn_url> Alphamining_agent_benchmark_cn

# 4. Qlib source (needed by DataPipeline scripts; clone into EACH experiment repo)
git clone https://github.com/microsoft/qlib.git Alphamining_agent_benchmark_us/qlib
git clone https://github.com/microsoft/qlib.git Alphamining_agent_benchmark_cn/qlib
```

### 3.1 Place AlphaAgent

AlphaAgent is not included in the benchmark harness. Place the source at
`AlphaAgent/` inside **each** experiment repo:

```bash
# Option A — clone directly into place
git clone <AlphaAgent_repo_url> Alphamining_agent_benchmark_us/AlphaAgent
git clone <AlphaAgent_repo_url> Alphamining_agent_benchmark_cn/AlphaAgent

# Option B — symlink one clone into both (saves disk, fine for read-only use)
git clone <AlphaAgent_repo_url> AlphaAgent
ln -s $(pwd)/AlphaAgent Alphamining_agent_benchmark_us/AlphaAgent
ln -s $(pwd)/AlphaAgent Alphamining_agent_benchmark_cn/AlphaAgent
```

### 3.2 Place QuantaAlpha

```bash
git clone https://github.com/QuantaAlpha/QuantaAlpha Alphamining_agent_benchmark_us/QuantaAlpha
git clone https://github.com/QuantaAlpha/QuantaAlpha Alphamining_agent_benchmark_cn/QuantaAlpha
```

After this step your tree should match the layout in §2.

---

## 4. Set up conda environments

The data-pipeline scripts and the host-side evaluator need two conda envs.
The Docker images are self-contained and do **not** use these envs at run time.

### 4.1 `alphaagent` env

```bash
conda create -n alphaagent python=3.10 -y
conda activate alphaagent

# Core deps from AlphaAgent
pip install -r Alphamining_agent_benchmark_us/AlphaAgent/requirements.txt

# Install the package in editable mode
SETUPTOOLS_SCM_PRETEND_VERSION_FOR_ALPHAAGENT=0.1.0 \
  pip install -e Alphamining_agent_benchmark_us/AlphaAgent/

# Extra deps (not in requirements.txt but imported at runtime)
pip install rich jinja2 scipy
pip install "pandas>=2.0.0" "numpy>=1.24.0"

# Qlib (needed for the DataPipeline and the evaluator)
pip install pyqlib   # or: pip install git+https://github.com/microsoft/qlib.git

# DataPipeline extras
pip install yahooquery akshare baostock fire
```

### 4.2 `quantaalpha` env

```bash
conda create -n quantaalpha python=3.10 -y
conda activate quantaalpha

# Qlib from source (no Linux ARM wheel on PyPI for 0.9.7)
pip install "git+https://github.com/microsoft/qlib.git@v0.9.7" \
  || pip install "git+https://github.com/microsoft/qlib.git"

# QuantaAlpha deps (skip the pyqlib line — already installed from git above)
grep -v pyqlib Alphamining_agent_benchmark_us/QuantaAlpha/requirements.txt \
  | pip install -r /dev/stdin

# Install the package
SETUPTOOLS_SCM_PRETEND_VERSION_FOR_QUANTAALPHA=0.1.0 \
  pip install -e Alphamining_agent_benchmark_us/QuantaAlpha/

pip install rich jinja2 scipy
```

### 4.3 Host evaluator env

The evaluator (`alphamining_benchmark/evaluator/run_eval.py`) runs on the host
after all containers finish. It needs Qlib and a few standard packages.
The `alphaagent` env already satisfies this — activate it when running the
evaluator standalone (§9).

---

## 5. Data pipeline — US (SP500)

Both AlphaAgent and QuantaAlpha share the same Qlib data directory for US:

```
~/.qlib/qlib_data/us_data/
```

Run the pipeline **once** — it covers both systems.
On Apple Silicon / macOS, prefix long steps with `caffeinate -i` to prevent
sleep from killing network connections mid-download.

```bash
conda activate alphaagent
cd ~/alphamining

caffeinate -i python \
  Alphamining_agent_benchmark_us/DataPipeline/AlphaAgent/us/build_data_pipeline.py
```

This runs four stages automatically:

| Stage | What it does | Duration |
|---|---|---|
| 1/4 `us_index/collector.py` | Scrapes S&P 500 historical membership from Wikipedia | ~5 min |
| 2/4 `yahoo/collector.py download_data` | Downloads OHLCV CSVs for ~858 SP500-ever tickers from Yahoo Finance | **2–4 hours** |
| 3/4 `yahoo/collector.py normalize_data` | Adjusts for splits/dividends | ~30 min |
| 4/4 `dump_bin.py dump_all` | Converts to Qlib binary format | ~20 min |

If the download is interrupted, restart with `--skip-download` **is not safe**
(Yahoo re-fetches from scratch). Instead just re-run the full command — the
script runs `dedupe_source_csvs` automatically to clean up duplicate rows.

To rebuild only stages 2–4 after a previous successful run:

```bash
python Alphamining_agent_benchmark_us/DataPipeline/AlphaAgent/us/build_data_pipeline.py \
  --skip-download --skip-normalize
```

**Verify the data loaded correctly:**

```python
conda activate alphaagent
python - <<'EOF'
import qlib
qlib.init(provider_uri="~/.qlib/qlib_data/us_data", region="us")
from qlib.data import D
df = D.features(D.instruments("SP500"), ["$close"], start_time="2023-01-01", end_time="2023-01-10")
print(df.head())
EOF
```

---

## 6. Data pipeline — CN (CSI500 + CSI300)

The CN side has **two separate datasets** — do not merge them.

### 6.1 AlphaAgent CN data (CSI500) → `~/.qlib/qlib_data/cn_data`

```bash
conda activate alphaagent
caffeinate -i python \
  Alphamining_agent_benchmark_cn/DataPipeline/AlphaAgent/china/build_data_pipeline.py
```

Stages:

| Stage | What it does | Duration |
|---|---|---|
| 1/4 Baostock download | Downloads raw OHLCV for all A-share stocks | **1–2 hours** |
| 2/4 `dump_bin.py` | Converts to Qlib binary | ~20 min |
| 3/4 `future_calendar_collector.py` | Builds CN trading calendar | ~5 min |
| 4/4 `cn_index/collector.py` | Fetches CSI500 point-in-time membership | ~5 min |

Unlike the US pipeline, the Baostock download IS incremental — re-running
`--skip-download` safely skips stage 1:

```bash
python Alphamining_agent_benchmark_cn/DataPipeline/AlphaAgent/china/build_data_pipeline.py \
  --skip-download
```

### 6.2 QuantaAlpha CN data (CSI300) → `~/.qlib/qlib_data/quantaalpha_cn_data`

QuantaAlpha ships a prebuilt HuggingFace bundle (~900 MB total) instead of
building from raw data.

```bash
conda activate quantaalpha
python \
  Alphamining_agent_benchmark_cn/DataPipeline/QuantaAlpha/china/build_data_pipeline.py
```

This downloads `cn_data.zip`, `daily_pv.h5`, and `daily_pv_debug.h5` from
`https://huggingface.co/datasets/QuantaAlpha/qlib_csi300` and extracts them.

After the download, copy the `.h5` files into QuantaAlpha's expected workspace:

```bash
QA_DIR=~/alphamining/Alphamining_agent_benchmark_cn/QuantaAlpha
DP_DIR=~/alphamining/Alphamining_agent_benchmark_cn/DataPipeline/QuantaAlpha/china

mkdir -p "$QA_DIR/git_ignore_folder/factor_implementation_source_data"
mkdir -p "$QA_DIR/git_ignore_folder/factor_implementation_source_data_debug"

cp "$DP_DIR/data_output/daily_pv.h5" \
   "$QA_DIR/git_ignore_folder/factor_implementation_source_data/daily_pv.h5"
cp "$DP_DIR/data_output_debug/daily_pv_debug.h5" \
   "$QA_DIR/git_ignore_folder/factor_implementation_source_data_debug/daily_pv.h5"
```

Repeat the same steps for `Alphamining_agent_benchmark_us/QuantaAlpha/` (US side
uses the same QuantaAlpha binary, pointing at `us_data`):

```bash
QA_DIR=~/alphamining/Alphamining_agent_benchmark_us/QuantaAlpha
DP_DIR=~/alphamining/Alphamining_agent_benchmark_us/DataPipeline/QuantaAlpha/us
mkdir -p "$QA_DIR/git_ignore_folder/factor_implementation_source_data"
# The US pipeline produces daily_pv.h5 from us_data; copy it likewise.
```

### 6.3 Summary: which data goes where

| System | Universe | Qlib data dir | `daily_pv.h5` location |
|---|---|---|---|
| AlphaAgent (US) | SP500 | `~/.qlib/qlib_data/us_data` | N/A |
| QuantaAlpha (US) | SP500 | `~/.qlib/qlib_data/us_data` | `QuantaAlpha/git_ignore_folder/factor_implementation_source_data/` |
| AlphaAgent (CN) | CSI500 | `~/.qlib/qlib_data/cn_data` | N/A |
| QuantaAlpha (CN) | CSI300 | `~/.qlib/qlib_data/quantaalpha_cn_data` | `QuantaAlpha/git_ignore_folder/factor_implementation_source_data/` |

---

## 7. Build Docker images

The `build.sh` scripts copy the system source from `SYSTEM_REPO`, merge it with
the benchmark's `adapter.py` and `entrypoint.sh`, and run `docker build`.

### 7.1 AlphaAgent images

```bash
cd ~/alphamining

# US image
SYSTEM_REPO=$(pwd)/Alphamining_agent_benchmark_us \
  bash alphamining_benchmark/systems/alphaagent/build.sh

# CN image (default; no SYSTEM_REPO override needed)
bash alphamining_benchmark/systems/alphaagent/build.sh
```

Both produce the same tag `alphamining/alphaagent:latest` — build US last if you
want the US variant ready for the next step, or re-tag:

```bash
# Tag separately if you want both simultaneously
SYSTEM_REPO=$(pwd)/Alphamining_agent_benchmark_us \
  TAG=alphamining/alphaagent-us:latest \
  bash alphamining_benchmark/systems/alphaagent/build.sh

TAG=alphamining/alphaagent-cn:latest \
  bash alphamining_benchmark/systems/alphaagent/build.sh
```

### 7.2 QuantaAlpha images

```bash
SYSTEM_REPO=$(pwd)/Alphamining_agent_benchmark_us \
  bash alphamining_benchmark/systems/quantaalpha/build.sh

bash alphamining_benchmark/systems/quantaalpha/build.sh
```

### 7.3 Verify images exist

```bash
docker images | grep alphamining
# alphamining/alphaagent    latest   ...   ~4.8 GB
# alphamining/quantaalpha   latest   ...   ~5.8 GB
```

> **Apple Silicon note:** images are built for `linux/aarch64` (native). If you
> need to run them on an x86_64 host, add `--platform linux/amd64` to the
> `docker build` line in each `build.sh`.

---

## 8. Run the experiments

### 8.1 Set your API credentials

```bash
export LLM_API_KEY=sk-...                      # your OpenAI / DeepSeek / etc. key
export LLM_API_BASE=https://api.openai.com/v1  # or deepseek, vLLM, etc.
```

These are injected into every container as `OPENAI_API_KEY` / `OPENAI_BASE_URL`
by the entrypoints — never hardcode them.

### 8.2 SP500 experiment

```bash
cd ~/alphamining/alphamining_benchmark

python orchestrator/run_experiment.py \
  --systems alphaagent quantaalpha \
  --universe SP500 \
  --backbone gpt-4.1 \
  --runs 1 \
  --loop-n 5 \
  --dev-data-dir  ~/.qlib/qlib_data/us_data \
  --test-data-dir ~/.qlib/qlib_data/us_data \
  --output-dir    results/exp_us_001 \
  --llm-api-key   "$LLM_API_KEY" \
  --llm-api-base  "$LLM_API_BASE" \
  --budget-usd    50
```

### 8.3 CSI500 experiment (AlphaAgent only)

```bash
python orchestrator/run_experiment.py \
  --systems alphaagent \
  --universe csi500 \
  --backbone gpt-4.1 \
  --runs 1 \
  --loop-n 5 \
  --dev-data-dir  ~/.qlib/qlib_data/cn_data \
  --test-data-dir ~/.qlib/qlib_data/cn_data \
  --output-dir    results/exp_cn_001 \
  --llm-api-key   "$LLM_API_KEY" \
  --llm-api-base  "$LLM_API_BASE" \
  --budget-usd    50
```

> QuantaAlpha on CN uses a different data directory (`quantaalpha_cn_data`) that
> cannot be passed alongside AlphaAgent's `cn_data` in a single orchestrator run.
> Run them separately and combine the resulting `candidates.parquet` files in §9.

### 8.4 Controlling the CoSTEER inner loop (AlphaAgent cost guard)

AlphaAgent's Factor Coder uses a retry loop (`max_loop=10`, `fail_task_trial_limit=20`
by default) that can spiral into hundreds of LLM calls per outer iteration when a
factor fails to execute. Pass these env vars to cap it:

```bash
python orchestrator/run_experiment.py \
  --systems alphaagent \
  ... \
  # Add these to the docker run via a wrapper, or set them in the entrypoint
```

Alternatively, set them in `systems/alphaagent/entrypoint.sh` before building
the image:

```bash
# Add to alphamining_benchmark/systems/alphaagent/entrypoint.sh
export FACTOR_CoSTEER_max_loop=3
export FACTOR_CoSTEER_fail_task_trial_limit=5
```

Then rebuild (`bash systems/alphaagent/build.sh`) before running.

### 8.5 Monitoring progress

Token usage is written to `/output/token_usage.json` inside each container and
therefore appears on the host at:

```
results/exp_us_001/alphaagent/run00/token_usage.json
results/exp_us_001/quantaalpha/run00/token_usage.json
```

To watch it live while a container is running:

```bash
watch -n 10 cat results/exp_us_001/alphaagent/run00/token_usage.json
```

To list running containers:

```bash
docker ps
```

---

## 9. Evaluate results

The orchestrator calls the evaluator automatically after all containers finish.
To re-run evaluation on existing `candidates.parquet` files (e.g. after changing
selector settings):

```bash
conda activate alphaagent
cd ~/alphamining/alphamining_benchmark

python evaluator/run_eval.py \
  --candidates \
    results/exp_us_001/alphaagent/run00/candidates.parquet \
    results/exp_us_001/quantaalpha/run00/candidates.parquet \
  --data-dir   ~/.qlib/qlib_data/us_data \
  --universe   SP500 \
  --output     results/exp_us_001/metrics_rerun.json \
  --selector-mode standalone \
  --max-factors 50
```

`--selector-mode marginal` runs greedy forward selection by marginal IC gain over
Alpha158 (more accurate, significantly slower).

---

## 10. Output structure

After a full experiment run:

```
results/exp_us_001/
  experiment.json                   run metadata (systems, universe, backbone, loop_n)
  alphaagent/
    run00/
      candidates.parquet            all factors generated by AlphaAgent
      token_usage.json              cumulative token counts + call count
  quantaalpha/
    run00/
      candidates.parquet
      token_usage.json
  metrics.json                      ΔRankIC, ΔNet IR, base/enhanced breakdown
  summary.json                      run counts + failed runs + metrics combined
```

### `candidates.parquet` schema

| Column | Type | Description |
|---|---|---|
| `factor_name` | str | unique identifier |
| `formula` | str | mathematical expression |
| `code` | str | Python implementation |
| `dev_rankic` | float | mean cross-sectional rank IC on val period (2021–22) |
| `dev_ic_ir` | float | IC information ratio on val period |
| `iteration` | int | outer mining round that produced this factor |
| `system` | str | `alphaagent` or `quantaalpha` |
| `backbone` | str | LLM model name |
| `universe` | str | target universe |
| `valid` | bool | factor executed without error |
| `error` | str | error message if `valid=False` |

### Key metrics in `metrics.json`

| Key | Meaning |
|---|---|
| `delta_rankic` | mean daily RankIC of (Alpha158 + selected factors) minus Alpha158 alone |
| `delta_net_ir` | net information ratio enhancement at 10 bps one-way cost |
| `base` | Alpha158-only model results |
| `enhanced` | Alpha158 + selected factors results |
| `n_selected` | number of factors selected by the selector |

---

## 11. Cost and time estimates

Based on our runs with `gpt-4.1`, `loop_n=5`, single run per system:

| Run | Input tokens | Output tokens | Approx. cost | Wall time |
|---|---|---|---|---|
| AlphaAgent SP500 (loop_n=5) | ~300–500 K | ~80–150 K | ~$2–4 | 2–4 hours |
| QuantaAlpha SP500 (loop_n=5) | ~200–400 K | ~60–120 K | ~$1.5–3 | 1–3 hours |

Pricing at `gpt-4.1` rates: $1.75/M input, $0.175/M cached input, $14.00/M output.

**Cost guard:** pass `--budget-usd 50` to the orchestrator. The container itself
does not enforce this limit automatically — monitor `token_usage.json` and kill
the container if it exceeds your budget:

```bash
docker kill <container_id>
```

---

## 12. Troubleshooting

**`unrecognized index type datetime64[ns]`** inside the AlphaAgent container

Pandas version mismatch: the container is reading HDF5 files written by a newer
host pandas. Fixed by the `pip install "pandas>=2.0.0"` layer in the Dockerfile
— rebuild the image.

**`ModuleNotFoundError: No module named 'rich'`**

The `rich` package is not in AlphaAgent's `requirements.txt` but is imported at
runtime. Fixed by the `pip install rich jinja2 scipy` layer — rebuild.

**`pyqlib` fails to install (Linux ARM / aarch64)**

No ARM wheel on PyPI for pyqlib 0.9.7. The QuantaAlpha Dockerfile installs from
git source instead — rebuild if you see this error on a fresh build.

**AlphaAgent container consuming thousands of tokens and not progressing**

Root cause: CoSTEER's inner retry loop (`max_loop=10`, `fail_task_trial_limit=20`)
spirals when generated factor code fails to execute. Set lower limits in
`entrypoint.sh` (see §8.4) and rebuild before running.

**QuantaAlpha `instrument not exists: csi300`**

The container's `QLIB_DATA_DIR` points at AlphaAgent's `cn_data` instead of
`quantaalpha_cn_data`. Check the `.env` file in `Alphamining_agent_benchmark_cn/QuantaAlpha/`
and make sure `QLIB_DATA_DIR=~/.qlib/qlib_data/quantaalpha_cn_data`.

**`No calendar dates found for dev period`**

The Qlib data directory was not fully built. Re-run the data pipeline for the
relevant universe and verify with the snippet in §5.

**QuantaAlpha fails with `~/.qlib/qlib_data/us_data: no such file`**

The entrypoint creates a symlink `~/.qlib/qlib_data/us_data → $QLIB_DATA_DIR`.
If `QLIB_DATA_DIR` is empty, the symlink target doesn't exist. Make sure the
`--dev-data-dir` passed to the orchestrator contains the built Qlib data.
