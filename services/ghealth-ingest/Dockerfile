FROM golang:1.24-bookworm AS ghealth-builder

ARG GHEALTH_GIT_REF=9cf02743d9ca051500b7c1c181eb88a9ae8988a5
RUN git clone https://github.com/Google-Health-API/google-health-cli.git /src \
    && cd /src \
    && git checkout --detach "$GHEALTH_GIT_REF" \
    && git rev-parse HEAD | grep -Fx "$GHEALTH_GIT_REF" \
    && go build -trimpath -ldflags='-s -w' -o /out/ghealth .

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=America/New_York \
    GHEALTH_CONFIG_DIR=/run/ghealth GHEALTH_FORMAT=json
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=ghealth-builder /out/ghealth /usr/local/bin/ghealth
COPY app ./app
CMD ["python", "-m", "app.worker"]
