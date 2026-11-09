FROM python:3.12-slim

WORKDIR /srv
RUN useradd -m -u 10001 terra

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
USER terra

# Cloud Run (and most container hosts) inject the listening port as $PORT and
# ignore EXPOSE. Hardcoding 8000 makes the container start and then fail its
# health check with no useful error. Default to 8000 for local `docker run`.
ENV PORT=8000
EXPOSE 8000

CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
