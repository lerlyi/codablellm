# Contributing to CodableLLM

Thank you for your interest in contributing to **CodableLLM**! 🎉  
Whether you're fixing a bug, improving documentation, or adding support for a new language or feature — we appreciate your help.

---

## Development Setup

1. **Fork the repository** and clone your fork:

    ```bash
    git clone https://github.com/your-username/codablellm.git
    cd codablellm
    ```

2. **Create a virtual environment** (optional but recommended):

    ```bash
    python -m venv .venv
    source .venv/bin/activate # On Windows use: .venv\Scripts\Activate.ps1
    ```

3. **Install all extras and dev dependencies**:

    ```
    pip install .[all,dev]
    ```

4. **Run tests** to verify setup:

    ```bash
    pytest
    ```

## How to Contribute

1. **Open an issue**: Propose a bug fix, enhancement, or new feature by opening an issue.

## Testing

We use **pytest** for unit testing. You can run all tests with:

```bash
pytest
```

Please ensure all tests pass before opening a pull request.

## Code Style

We follow **PEP8** and use `autopep8` for auto-formatting. Our documentation style is [Google's Python Style](https://google.github.io/styleguide/pyguide.html).

## Commit Guidelines

This project uses conventional commits to automate versioning and changelogs with `release-please`.

Please use the following prefixes in your commit messages (or PR titles):

- `feat:` — for new features (triggers a **minor** version bump)
- `fix:` — for bug fixes (triggers a **patch** bump)
- `refactor:` — for code improvements (patch bump)
- `chore:` — for maintenance tasks (no version bump)
- `docs:` — for documentation updates (no version bump)
- `test:` — for test-related changes (no version bump)

**Examples:**

```
feat: add function to export datasets to Markdown
fix: handle edge case in Git repository parsing
chore: update GitHub Actions workflow
```