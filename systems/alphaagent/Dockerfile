FROM continuumio/miniconda3:23.10.0-1

RUN apt-get update && apt-get install -y git gcc g++ make && rm -rf /var/lib/apt/lists/*

# AlphaAgent pins pandas 1.5.3 and numpy 1.23.5; create isolated env
RUN conda create -n alphaagent python=3.10 -y

WORKDIR /app

# System code (copied in by build.sh from Alphamining_agent_benchmark_cn/AlphaAgent/)
COPY AlphaAgent/ /app/AlphaAgent/

# Install deps into the conda env
RUN conda run -n alphaagent pip install --no-cache-dir -r /app/AlphaAgent/requirements.txt
RUN conda run -n alphaagent pip install --no-cache-dir -e /app/AlphaAgent/

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
