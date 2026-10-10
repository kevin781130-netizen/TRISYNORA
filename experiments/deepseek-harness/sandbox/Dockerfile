# Test-only Docker OS boundary for OFFICIAL external DSH, no native projects.
# Build using a completely EMPTY context; never COPY TRISYNORA or product repos.
# Official NPM/native Node add-ons must be resolved ON THE TARGET image
# platform, never cross-mounted from the Ubuntu GitHub runner.
FROM node:24-trixie-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 bash ca-certificates git procps \
    && rm -rf /var/lib/apt/lists/*
# Package resolution and native add-on selection happen ONLY at build time.
# Runtime has no network and this immutable image contains no Git sources.
RUN mkdir -p /opt/dsh \
    && npm install --prefix /opt/dsh --no-audit --no-fund --ignore-scripts @deepseek-ai/dsh@0.2.0-rc.2
RUN groupadd -g 10001 sandbox && useradd -u 10001 -g 10001 -M -s /usr/sbin/nologin sandbox
USER 10001:10001
WORKDIR /tmp
ENV HOME=/tmp DSH_TELEMETRY_DISABLED=1 PYTHONDONTWRITEBYTECODE=1
# Runtime policy is controlled by docker run: --read-only --network=none,
# --cap-drop=ALL, --security-opt=no-new-privileges, no product mounts or host creds.
# This image must not be used as an authenticated native product adapter.
