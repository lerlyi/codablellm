# 3. The CodableLLM CLI

In addition to its Python library, CodableLLM provides a simple command-line interface (CLI) that allows you to perform the same core dataset generation workflows without writing Python code.

If you've followed along with the previous sections, you'll find that the CLI mirrors those same capabilities — extracting functions, decompiling binaries, and building datasets — all from the command line.

## Basic Usage

Once installed, you can invoke the CLI with:

```
codablellm <repo> <save_as> [bins...]
```

For a full list of commands and options, run:

```
codablellm --help
```