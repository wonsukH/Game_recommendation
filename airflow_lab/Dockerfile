FROM apache/airflow:2.10.5-python3.11

# build_ease_artifact stamps meta.json with `git rev-parse HEAD` and falls back to
# "unknown" on any exception. The base image has no git, so every artifact this
# stack produced was untraceable to the code that built it — a silent loss, since
# the fallback is a plain except.
#
# safe.directory is needed too: /opt/project is mounted root-owned and the tasks
# run as uid 50000, which trips git's dubious-ownership check.
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Versions are pinned to the project's requirements.txt, NOT to loose ranges.
#
# They were ranges at first, which resolved to pandas 3.0.5 while the project
# pins 2.3.1. That drift changed how a missing price_currency reaches
# build_catalog_db: pandas 2.x hands it over as None, 3.x as NaN. The value is
# written to catalog.json unguarded, so the artifact came out with a bare NaN in
# 2,391 entries — accepted by Python's json, rejected by any strict parser.
#
# The build ran, the gates passed, and the defect was only visible by diffing the
# output against the artifact the project already had. Pin, don't range.
#
# requirements.txt cannot be COPYed here: it lives at the repo root, and moving
# the build context up would ship the 2GB steam.db to the daemon. Keep these in
# step with requirements.txt by hand.
USER airflow
RUN git config --global --add safe.directory /opt/project \
    && pip install --no-cache-dir \
        "numpy==2.3.2" \
        "scipy==1.16.1" \
        "pandas==2.3.1" \
        "scikit-learn==1.7.1" \
        "requests==2.32.4" \
        "python-dotenv==1.1.1"
