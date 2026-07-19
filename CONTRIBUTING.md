# Contributing to TTS MultiModel

Thank you for your interest in contributing to TTS MultiModel! This guide will help you get started.

## 🌟 Ways to Contribute

- **Bug Reports**: Submit issues with detailed reproduction steps
- **Feature Requests**: Open an issue with the `enhancement` label
- **Code Contributions**: Fork → Branch → Commit → Push → Pull Request
- **Documentation**: Fix typos, add examples, improve translations
- **Testing**: Write and improve test coverage

## 🛠️ Development Setup

```bash
# Clone the repository
git clone https://github.com/ReSerendipity/TTS_MultiModel.git
cd TTS_MultiModel

# Install dependencies
pip install -r requirements.txt

# Install dev dependencies
pip install pytest pytest-asyncio pytest-cov ruff

# Run tests
pytest tests/ -v -k "not gpu and not cuda and not vram" -m "not integration"

# Run linter
ruff check bin/integrated_app/ scripts/

# Run formatter
ruff format bin/integrated_app/ scripts/
```

## 📋 Code Style

- Follow PEP 8 conventions
- Use `ruff` for linting and formatting
- Line length: 120 characters
- Type hints are encouraged for public APIs

## 🔄 Pull Request Process

1. **Fork** the repository
2. **Create a feature branch**: `git checkout -b feature/your-feature-name`
3. **Make your changes** with clear, concise commits
4. **Add tests** for new functionality
5. **Run the test suite**: `pytest tests/ -v`
6. **Run linter**: `ruff check bin/integrated_app/ scripts/`
7. **Submit a Pull Request** with a clear description

### Commit Messages

Use conventional commit format:

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `refactor:` Code refactoring
- `test:` Test additions/changes
- `chore:` Build/process changes

## 🐛 Bug Reports

When filing a bug report, please include:

1. **Environment**: OS, Python version, GPU type, PyTorch version
2. **Steps to reproduce**: Clear, step-by-step instructions
3. **Expected behavior**: What you expected to happen
4. **Actual behavior**: What actually happened
5. **Logs**: Relevant log output from `logs/app.log`

## 💡 Feature Requests

When suggesting a feature, please include:

1. **Use case**: Why is this feature needed?
2. **Proposed solution**: How should it work?
3. **Alternatives**: Any alternative approaches considered

## 🌍 Translations

We welcome translations for the web interface! Currently supported:

- Chinese (zh) - Complete
- English (en) - Complete
- Japanese (ja) - Complete
- Korean (ko) - Complete

To add a new language:

1. Create a new translation file in `bin/integrated_app/locales/`
2. Follow the existing translation file format
3. Submit a PR with the new translation

## 📜 License

By contributing, you agree that your contributions will be licensed under the MIT License.
