# Function Comment Augmentation

## Overview

In this example, we demonstrate how CodableLLM can be used to automatically generate descriptive function comments for C source code.

In large codebases, functions are often missing comments that describe their purpose, inputs, and outputs. Automatically generating these comments can:

- Improve code readability and maintainability  
- Provide training data for models focused on code summarization and instruction-following tasks  
- Help build better AI tools for automatic documentation generation

## Creating The Datasets

To support this use case, we generate two datasets:

1. A dataset of the **original** source code functions (undocumented)
2. A dataset of the **transformed** source code functions with generated comments (documented)

These can later be merged or aligned for training models on before-and-after examples.

```python
from codablellm import create_source_dataset, ExtractConfig, SourceCodeDatasetConfig, SourceCodeDataset

def add_docstring(source: SourceFunction) -> SourceFunction: ...
    # Use an LLM to generate a docstring for a function

# Original (undocumented) dataset
original_dataset = create_source_dataset(
    'path/to/demo-c-repo',
    config=SourceCodeDatasetConfig(
        generation_mode='path'  # Extracts code as-is
    )
)

# Transformed (documented) dataset
documented_dataset = create_source_dataset(
    'path/to/demo-c-repo',
    config=SourceCodeDatasetConfig(
        transform=add_docstring,
        generation_mode='temp'  # Applies transform to a temp copy
    )
)

# Save both for external merging or pairing
original_dataset.save_as('undocumented_dataset.csv')
documented_dataset.save_as('docstring_dataset.csv')
```

## Dataset Contents

The two datasets will contain:

- `undocumented_dataset.csv`: functions as they originally appear in the codebase
- `docstring_dataset.csv`: functions augmented with generated docstrings

You can pair them based on function metadata (e.g., `uid`, file path, line number) to build aligned training examples.

### Example

Undocumented Function Source Code:

```c
int add(int a, int b) {
    return a + b;
}
```

Documented Function Source Code:

```c
int add(int a, int b) {
    // Adds two integers and returns the result
    return a + b;
}
```

## Implications

By generating separate original and comment-augmented datasets:

- Models can learn to generate summaries and docstrings given raw source code
- This supports training instruction-following models for automatic code documentation
- Fine-tuned models built on this data can assist in documenting legacy codebases or poorly commented projects

