# Airflow, with this course's dependencies installed inside it.
#
# The DAG shells out to `python -m pipelines.p1_bronze_trips` and friends, so
# the worker needs everything a pipeline needs: a Postgres driver, a Kafka
# client, a Mongo client, an S3 client. Mounting the code without installing
# its dependencies gives you an Airflow that parses the DAG and fails every
# task, which is worse than no Airflow at all.
FROM apache/airflow:2.10.4-python3.12

COPY requirements.txt /tmp/requirements-airflow.txt
RUN pip install --no-cache-dir -r /tmp/requirements-airflow.txt
