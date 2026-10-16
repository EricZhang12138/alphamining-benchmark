FROM continuumio/miniconda3:latest

RUN apt-get update && apt-get install -y --fix-missing git gcc g++ make && rm -rf /var/lib/apt/lists/*

# QuantaAlpha uses pandas>=2.0 (incompatible with AlphaAgent's 1.5.3)
RUN conda create -n quantaalpha python=3.10 -y

WORKDIR /app

COPY QuantaAlpha/ /app/QuantaAlpha/

# pyqlib has no Linux ARM wheel on PyPI; install from source first, then remaining deps
RUN conda run -n quantaalpha pip install --no-cache-dir \
    "git+https://github.com/microsoft/qlib.git@v0.9.7" || \
    conda run -n quantaalpha pip install --no-cache-dir \
    "git+https://github.com/microsoft/qlib.git"
RUN grep -v pyqlib /app/QuantaAlpha/requirements.txt > /tmp/req_noqulib.txt && \
    conda run -n quantaalpha pip install --no-cache-dir -r /tmp/req_noqulib.txt
RUN SETUPTOOLS_SCM_PRETEND_VERSION_FOR_QUANTAALPHA=0.1.0 \
    conda run -n quantaalpha pip install --no-cache-dir -e /app/QuantaAlpha/
# Extra deps not in requirements.txt but imported at runtime
RUN conda run -n quantaalpha pip install --no-cache-dir rich jinja2 scipy

COPY adapter.py    /app/adapter.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Two bind mounts are required at docker run time (paths are user-supplied, not hardcoded):
#   -v <host_qlib_data_dir>:/data/dev:ro   any Qlib data dir on the host → read-only /data/dev
#   -v <host_output_dir>:/output           any writable dir on the host  → /output (candidates.parquet written here)
# The orchestrator passes these via --dev-data-dir and --output-dir; see orchestrator/run_experiment.py.

WORKDIR /app/QuantaAlpha
ENTRYPOINT ["/app/entrypoint.sh"]
