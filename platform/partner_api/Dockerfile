FROM python:3.13-slim
WORKDIR /srv
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" "psycopg[binary]"
COPY app.py .
EXPOSE 8088
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8088"]
