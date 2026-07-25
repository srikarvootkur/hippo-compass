ARG OPENCLAW_IMAGE=ghcr.io/openclaw/openclaw:latest

FROM golang:1.24-bookworm AS ghealth-builder
ARG GHEALTH_GIT_REF=9cf02743d9ca051500b7c1c181eb88a9ae8988a5
RUN git clone https://github.com/Google-Health-API/google-health-cli.git /src \
    && cd /src \
    && git checkout --detach "$GHEALTH_GIT_REF" \
    && git rev-parse HEAD | grep -Fx "$GHEALTH_GIT_REF" \
    && go build -trimpath -ldflags='-s -w' -o /out/ghealth .

FROM ${OPENCLAW_IMAGE}
USER root
COPY --from=ghealth-builder /out/ghealth /usr/local/bin/ghealth
USER node
