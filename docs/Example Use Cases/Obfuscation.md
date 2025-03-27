# Obfuscation

## Overview

In this example, we use CodableLLM to generate a dataset designed for function name recovery — the task of predicting a function's original name based on its source code or decompiled implementation.

This dataset can be used to train models for:

- Reverse engineering tasks  
- Deobfuscation tooling  
- Enhancing binary analysis by recovering semantic information from stripped binaries

## Creating the Datasets

To support this use case, we generate two datasets:

1. A dataset of the **original** source code and decompiled functions (deobfuscated)
2. A dataset of the **transformed** versions with obfuscated function names

These can be merged later using metadata to create aligned training pairs for function name recovery tasks.

```python
from codablellm import compile_dataset, DecompiledCodeDatasetConfig, ExtractConfig

def obfuscate_name(source: SourceFunction) -> SourceFunction: ...
    # Replace the function name with an ambiguous identifier (e.g., func_1)

# Original (deobfuscated) dataset
deobfuscated_dataset = compile_dataset(
    'path/to/demo-c-repo',
    [
        'path/to/demo-c-repo/main_app',
        'path/to/demo-c-repo/tool',
    ],
    'make',
    dataset_config=DecompiledCodeDatasetConfig(
        extract_config=ExtractConfig(),
        generation_mode='path'  # No transformation
    )
)

# Transformed (obfuscated) dataset
obfuscated_dataset = compile_dataset(
    'path/to/demo-c-repo',
    [
        'path/to/demo-c-repo/main_app',
        'path/to/demo-c-repo/tool',
    ],
    'make',
    dataset_config=DecompiledCodeDatasetConfig(
        extract_config=ExtractConfig(
            transform=obfuscate_name
        ),
        generation_mode='temp'  # Applies transform in a temp copy
    )
)

deobfuscated_dataset.save_as('deobfuscated_dataset.csv')
obfuscated_dataset.save_as('obfuscated_dataset.csv')
