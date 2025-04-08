# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12-slim
FROM python:${PYTHON_VERSION} AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies
USER root
RUN apt-get update && apt-get install -y \
    wget unzip sudo git build-essential gcc g++ make procps tini \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install OpenJDK 21 from Azul Zulu
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    ca-certificates \
    && curl -fsSL https://repos.azul.com/azul-repo.key | gpg --dearmor -o /usr/share/keyrings/azul.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/azul.gpg] https://repos.azul.com/zulu/deb stable main" > /etc/apt/sources.list.d/zulu.list \
    && apt-get update && apt-get install -y zulu21-jdk \
    && rm -rf /var/lib/apt/lists/*

# Set JAVA_HOME and update PATH
ENV JAVA_HOME="/usr/lib/jvm/zulu21"
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# Install Ghidra (adjust version as needed)
# Starts hanging in versions >= 11.2
ENV GHIDRA_VERSION=11.3.1
ENV GHIDRA_RELEASE_DATE=20250219
RUN wget https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_${GHIDRA_VERSION}_build/ghidra_${GHIDRA_VERSION}_PUBLIC_${GHIDRA_RELEASE_DATE}.zip \
    && unzip ghidra_${GHIDRA_VERSION}_PUBLIC_${GHIDRA_RELEASE_DATE}.zip -d /opt \
    && rm ghidra_${GHIDRA_VERSION}_PUBLIC_${GHIDRA_RELEASE_DATE}.zip

# Add Ghidra to PATH
ENV GHIDRA_HOME=/opt/ghidra_${GHIDRA_VERSION}_PUBLIC
ENV GHIDRA_HEADLESS=${GHIDRA_HOME}/support/analyzeHeadless
ENV PATH="${GHIDRA_HOME}:${PATH}"

# Create non-root user
ARG UID=10001
RUN adduser --disabled-password --gecos "" --shell "/sbin/nologin" --uid "${UID}" appuser \
    && usermod -aG sudo appuser

# Install core package tools
RUN python -m pip install --upgrade pip setuptools

# Copy pyproject.toml and install deps (cached if unchanged)
COPY pyproject.toml .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install .[all] --no-build-isolation

# Copy the source code (invalidates cache if you change code)
COPY . .

# Reinstall local package to pick up code changes
RUN pip install --no-deps --no-build-isolation .

# Optional: autocomplete
# RUN codablellm --install-completion

USER appuser

# To reap zombie processes created by Ghidra
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["codablellm"]
