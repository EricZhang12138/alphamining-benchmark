FROM continuumio/miniconda3:23.10.0-1

RUN apt-get update && apt-get install -y git gcc g++ make && rm -rf /var/lib/apt/lists/*

# QuantaAlpha uses pandas>=2.0 (incompatible with AlphaAgent's 1.5.3)
RUN conda create -n quantaalpha python=3.11 -y

WORKDIR /app

COPY QuantaAlpha/ /app/QuantaAlpha/

RUN conda run -n quantaalpha pip install --no-cache-dir -r /app/QuantaAlpha/requirements.txt
RUN conda run -n quantaalpha pip install --no-cache-dir -e /app/QuantaAlpha/

COPY adapter.py    /app/adapter.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Two bind mounts are required at docker run time (paths are user-supplied, not hardcoded):
#   -v <host_qlib_data_dir>:/data/dev:ro   any Qlib data dir on the host → read-only /data/dev
#   -v <host_output_dir>:/output           any writable dir on the host  → /output (candidates.parquet written here)
# The orchestrator passes these via --dev-data-dir and --output-dir; see orchestrator/run_experiment.py.

WORKDIR /app/QuantaAlpha
ENTRYPOINT ["/app/entrypoint.sh"]
