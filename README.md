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

### Docker

Alternatively, you can build and run CodableLLM's CLI using Docker:

**Build the image:**

```
docker build -t codablellm .
```

**Run the container with access to your local files:**

```bash
docker run --rm -it -v $(pwd):/workspace -w /workspace codablellm \
    codablellm --url https://github.com/dmanuel64/codablellm/raw/refs/heads/main/examples/demo-c-repo.zip \
    --build "cd /tmp/demo-c-repo && make" \
    /tmp/demo-c-repo demo-c-repo.csv /tmp/demo-c-repo
```

> **This mounts your current directory to /workspace inside the container, allowing access to input/output files.**

## Features

- Extracts functions and methods from source code repositories using [tree-sitter](https://github.com/tree-sitter/tree-sitter).
- Easy integration with LLMs to refine or augment extracted code (e.g. rename variables, insert comments, etc.)
- Language-agnostic design with support for plugin-based extractor and decompiler extensions.
- Extendable API for building your own workflows and datasets.

## Documentation

Complete documentation is available on [Read the Docs](https://codablellm.readthedocs.io/):

- [User Guide](https://codablellm.readthedocs.io/en/latest/User%20Guide/)
- [Supported Languages & Decompilers](https://codablellm.readthedocs.io/en/latest/Built-In%20Support/)
- [API Reference](https://codablellm.readthedocs.io/en/latest/documentation/codablellm/)

## Contributing

We welcome contributions from the community! See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines, development setup, and how to get started.