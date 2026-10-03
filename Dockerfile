FROM apache/airflow:3.1.8

COPY requirements.txt /requirements.txt

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends libstdc++6 \
    && rm -rf /var/lib/apt/lists/*
USER airflow

RUN pip install --no-cache-dir -r /requirements.txt
