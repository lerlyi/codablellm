<!-- markdownlint-disable MD041 -->
![Build Status](https://github.com/dmanuel64/codablellm/actions/workflows/test.yml/badge.svg?branch=main)
![Python Version](https://img.shields.io/pypi/pyversions/codablellm)
![PyPI](https://img.shields.io/pypi/v/codablellm)
![Downloads](https://img.shields.io/pypi/dm/codablellm)
![License](https://img.shields.io/github/license/dmanuel64/codablellm)
![Documentation Status](https://readthedocs.org/projects/codablellm/badge/?version=latest)

# CodableLLM

**CodableLLM** is a Python framework for creating and curating high-quality code datasets tailored for training and evaluating large language models (LLMs). It supports source code and decompiled code extraction, with a flexible architecture for handling multiple languages and integration with custom LLM prompts.

## Installation

### PyPI

Install CodableLLM directly from PyPI:

```bash
pip install codablellm
```

### Docker Compose (Recommended)

CodableLLM uses [Prefect](https://www.prefect.io/) for orchestration and parallel processing.
Because Prefect relies on a backend database, we recommend using the provided Docker Compose setup, which includes a configured PostgreSQL database.

**Run an example extraction using Docker Compose(Modified)**:

```bash
docker compose run --rm app \
  codablellm \
  /tmp/demo-c-repo \
  ./demo-c-repo.csv \
  /tmp/demo-c-repo/main_app \
  --url https://github.com/dmanuel64/codablellm/raw/refs/heads/main/examples/demo-c-repo.zip \
  --build make \
  --generation-mode temp-append \
  --symbol-remover strip
```
This command does the following:

--url https://... - URL for downloading the archive with source code

--build make - command to build the project (in this case make is used)

--generation-mode temp-append - dataset generation mode:

temp - uses temporary directory

append - appends transformed code to the original code in the output file

--symbol-remover strip - removes debugging symbols from compiled binaries

> **This uses the `app` service defined in `docker-compose.yml`, giving you access to the full environment including Prefect and PostgreSQL, which are required for managing flows and task state.**

## Features

- Extracts functions and methods from source code repositories using [tree-sitter](https://github.com/tree-sitter/tree-sitter).
- Easy integration with LLMs to refine or augment extracted code (e.g. rename variables, insert comments, etc.)
- Language-agnostic design with support for plugin-based extractor and decompiler extensions.
- Extendable API for building your own workflows and datasets.
- Fast and scalable, using Prefect to orchestrate and parallelize code extraction, transformation, and dataset generation across multiple processes and tasks.

## Documentation

Complete documentation is available on [Read the Docs](https://codablellm.readthedocs.io/):

- [User Guide](https://codablellm.readthedocs.io/en/latest/User%20Guide/)
- [Supported Languages & Decompilers](https://codablellm.readthedocs.io/en/latest/Built-In%20Support/)
- [API Reference](https://codablellm.readthedocs.io/en/latest/documentation/codablellm/)

## Contributing

We welcome contributions from the community! See [CONTRIBUTING.md](https://github.com/dmanuel64/codablellm/blob/main/CONTRIBUTING.md) for guidelines, development setup, and how to get started.
