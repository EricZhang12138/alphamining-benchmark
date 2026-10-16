FROM continuumio/miniconda3:latest

RUN apt-get update && apt-get install -y --fix-missing git gcc g++ make && rm -rf /var/lib/apt/lists/*

# AlphaAgent pins pandas 1.5.3 and numpy 1.23.5; create isolated env
RUN conda create -n alphaagent python=3.10 -y

WORKDIR /app

# System code (copied in by build.sh from Alphamining_agent_benchmark_cn/AlphaAgent/)
COPY AlphaAgent/ /app/AlphaAgent/

# Install deps into the conda env
RUN conda run -n alphaagent pip install --no-cache-dir -r /app/AlphaAgent/requirements.txt
RUN SETUPTOOLS_SCM_PRETEND_VERSION_FOR_ALPHAAGENT=0.1.0 \
    conda run -n alphaagent pip install --no-cache-dir -e /app/AlphaAgent/
# Extra deps not in requirements.txt but imported at runtime
RUN conda run -n alphaagent pip install --no-cache-dir rich jinja2 scipy
# Qlib data on the host was written with pandas 2.x; override the 1.5.3 pin so
# HDF5 files are readable inside the container
RUN conda run -n alphaagent pip install --no-cache-dir "pandas>=2.0.0" "numpy>=1.24.0"

# Benchmark adapter and entrypoint (also copied in by build.sh)
COPY adapter.py /app/adapter.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Two bind mounts are required at docker run time (paths are user-supplied, not hardcoded):
#   -v <host_qlib_data_dir>:/data/dev:ro   any Qlib data dir on the host → read-only /data/dev
#   -v <host_output_dir>:/output           any writable dir on the host  → /output (candidates.parquet written here)
# The orchestrator passes these via --dev-data-dir and --output-dir; see orchestrator/run_experiment.py.

WORKDIR /app/AlphaAgent
ENTRYPOINT ["/app/entrypoint.sh"]
