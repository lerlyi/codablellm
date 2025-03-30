# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12-slim
FROM python:${PYTHON_VERSION} AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies including Java for Ghidra
USER root
RUN apt-get update && apt-get install -y \
    openjdk-17-jdk wget unzip sudo git build-essential gcc g++ make \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Ghidra (adjust version as needed)
ENV GHIDRA_VERSION=11.0.1
ENV GHIDRA_RELEASE_DATE=20240130
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

# Install Python requirements
COPY . .
RUN python -m pip install --upgrade pip
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install .[all]

# Copy source and install package
COPY . .
RUN python -m pip install .[all]

# Optional: autocomplete
# RUN codablellm --install-completion

USER appuser

CMD ["codablellm"]
