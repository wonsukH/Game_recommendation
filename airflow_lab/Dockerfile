FROM apache/airflow:2.10.5-python3.11

# The P5 rebuild scripts need the numeric stack. Airflow itself pulls none of
# these, so they resolve independently of the Airflow constraint set.
USER airflow
RUN pip install --no-cache-dir \
        "numpy>=2,<3" \
        "scipy>=1.13" \
        "pandas>=2.2" \
        "scikit-learn>=1.5" \
        requests \
        python-dotenv
