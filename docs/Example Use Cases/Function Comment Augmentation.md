# Function Comment Augmentation

## Overview

In this example, we demonstrate how CodableLLM can be used to automatically generate descriptive function comments for C source code.

In large codebases, functions are often missing comments that describe their purpose, inputs, and outputs. Automatically generating these comments can:

- Improve code readability and maintainability  
- Provide training data for models focused on code summarization and instruction-following tasks  
- Help build better AI tools for automatic documentation generation

## Creating The Dataset

```python
from codablellm import create_source_dataset, ExtractConfig, SourceCodeDatasetConfig

def add_docstring(source: SourceFunction) -> SourceFunction: ...
    # Use an LLM to generate a docstring for a function

dataset = codablellm.create_source_dataset(
    'path/to/demo-c-repo',
    config=SourceCodeDatasetConfig(
        transform=add_docstring,
        generation_mode='temp-append' # Include both undocumented & documented code
    )
)

dataset.save_as('docstring_dataset.csv')
```

## Dataset Contents

Inside `docstring_dataset.csv`, each function will be included twice:

- The original, undocumented version
- The transformed version with an auto-generated comment

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

By generating comment-augmented datasets for codebases:

- Models can learn to generate summaries for both high-level and low-level code functions.
- Fine-tuned models can help write documentation for legacy codebases.