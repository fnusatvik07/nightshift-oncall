# One image, two services.
#
# The signal board and the agent system share every dependency and all of the
# project code, so building one image and running it with two different
# commands is simpler than maintaining two Dockerfiles that drift apart.
#
# The project is mounted rather than copied in development, so editing a KPI on
# your laptop changes what the running service does without a rebuild. For a
# real deployment you would COPY it in and pin the tag.
FROM python:3.13-slim

WORKDIR /app

# curl for the healthchecks, git because the lineage tools read history
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl git \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-oncall.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-oncall.txt

COPY . .

ENV PYTHONPATH=/app PYTHONUNBUFFERED=1

# overridden per service in docker-compose.yml
CMD ["uvicorn", "signal_service.api:app", "--host", "0.0.0.0", "--port", "8091"]
