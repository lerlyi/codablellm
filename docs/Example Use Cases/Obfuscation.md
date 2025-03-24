# Obfuscation

## Overview

In this example, we use CodableLLM to generate a dataset designed for function name recovery — the task of predicting a function's original name based on its source code or decompiled implementation.

This dataset can be used to train models for:

- Reverse engineering tasks  
- Deobfuscation tooling  
- Enhancing binary analysis by recovering semantic information from stripped binaries

## Creating The Dataset

In this demonstration, we locate function names in C source code and replace the name with an ambiguous identifier.

We will use the `DecompiledCodeDataset` generation pipeline with the `temp-append` mode, which automatically includes both the original (deobfuscated) and transformed (obfuscated) functions in the dataset. The dataset will consist of both source code and decompiled function pairs, making it ideal for both source-level and binary-level function name recovery research.

```python
from codablellm import compile_dataset, DecompiledCodeDatasetConfig, ExtractorConfig, \
    SourceFunction

def obfuscate_name(source: SourceFunction) -> SourceFunction: ...
    # Replace the function name with an ambiguous name

dataset = compile_dataset(
    'path/to/demo-c-repo',
    [
        'path/to/demo-c-repo/main_app',
        'path/to/demo-c-repo/tool',
    ],
    'make',
    dataset_config=DecompiledCodeDatasetConfig(
        extract_config=ExtractConfig(
            transform=add_one_to_array_access
        )
        generation_mode='temp-append' # Include both obfuscated & deobfuscated examples
    )
)

dataset.save_as('obfuscated_dataset.csv')
```

## Dataset Contents

Inside `obfuscated_dataset.csv`, each function will be included twice:

- The original, deobfuscated version
- The transformed version with an obfuscated function name

In addition to source-level transformations, the dataset will also contain decompiled representations of both the obfuscated and deobfuscated versions. This makes the dataset valuable for training models on both source code function name recovery and binary analysis tasks.

### Example

Deobfuscated Function Source Code:

```c
int add(int a, int b) {
    return a + b;
}
```

Obfuscated Function Source Code:

```c
int func_1(int a, int b) {
    return a + b;
}
```

## Implications

By generating function name obfuscation datasets:

- We can train models to predict descriptive function names from both source and decompiled code.
- This capability is extremely valuable for reverse engineering and security tooling.
- It enables automatic analysis of stripped binaries where symbol names are unavailable.