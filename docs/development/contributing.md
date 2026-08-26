# Contributing to hyper2kvm

Thank you for your interest in contributing to hyper2kvm!

## 📦 Repository Locations

hyper2kvm is available on multiple platforms:

- **GitHub (Primary)**: https://github.com/ssahani/hyper2kvm
- **GitLab (Mirror)**: https://gitlab.com/ssahani/hyper2kvm - Auto-synced from GitHub
- **PyPI**: https://pypi.org/project/hyper2kvm/

**Note:** All development happens on GitHub. GitLab is an automatic mirror for users who prefer that platform.

## 🔄 GitLab Mirror Setup

The GitLab repository automatically syncs from GitHub using:
- **Method**: GitLab Pull Mirroring
- **Frequency**: Every 5 minutes
- **Source**: https://github.com/ssahani/hyper2kvm
- **Target**: https://gitlab.com/ssahani/hyper2kvm

### For Maintainers: Mirror Configuration

If you need to set up mirroring on a new repository:

1. Go to GitLab: Settings → Repository → Mirroring repositories
2. Add mirror:
   - **Git repository URL**: `https://github.com/ssahani/hyper2kvm.git`
   - **Mirror direction**: Pull
   - **Authentication**: Use GitHub Personal Access Token with `repo` scope
3. Enable: "Mirror only protected branches" (optional)
4. Click: "Mirror repository"

The mirror will automatically pull changes every 5 minutes.

## 🚀 Getting Started

### Prerequisites

- **Python**: 3.10 or higher
- **Operating System**: Linux (Fedora/RHEL recommended), macOS, or Windows (WSL)
- **System Dependencies**:
  - qemu-img
  - qemu-nbd (for VMCraft, the default backend)

### Development Setup

```bash
# Clone the repository
git clone https://github.com/ssahani/hyper2kvm.git
cd hyper2kvm

# Install system dependencies (Fedora/RHEL)
# VMCraft is the default backend
sudo dnf install -y qemu-img qemu-nbd python3-hivex

# Install Python dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/unit/ -v
```

See [BUILDING.md](BUILDING.md) for complete build and development instructions.

## 📝 Pull Request Guidelines

### Before Submitting

1. **Test your changes**:
   ```bash
   pytest tests/unit/ -v
   make lint
   ```

2. **Follow code style**:
   - We use `ruff` for linting and formatting
   - Run `make fmt` to auto-format
   - Line length: 120 characters

3. **Write clear commit messages**:
   ```
   feat: Add support for btrfs subvolume detection

   - Implement _parse_btrfs_subvol() helper
   - Update mount.py to handle subvol= option
   - Add tests for subvolume path sanitization
   ```

4. **Update documentation** if needed

### Commit Message Format

We follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `style:` Code style changes (formatting, etc.)
- `refactor:` Code refactoring
- `test:` Adding or updating tests
- `chore:` Maintenance tasks

### Pull Request Process

1. **Fork the repository** (if you're not a maintainer)
2. **Create a feature branch**: `git checkout -b feat/my-feature`
3. **Make your changes** with clear commits
4. **Push to your fork**: `git push origin feat/my-feature`
5. **Open a Pull Request** on GitHub
6. **Address review feedback**

**Note**: Do NOT open PRs on GitLab - it's a read-only mirror. All PRs go to GitHub.

## 🧪 Testing

### Run Tests

```bash
# All unit tests
pytest tests/unit/ -v

# With coverage
pytest tests/unit/ --cov=hyper2kvm --cov-report=html

# Specific test file
pytest tests/unit/test_fixers/test_fstab_conversion.py -v
```

### Writing Tests

- Place tests in `tests/unit/` matching the source structure
- Use descriptive test names: `test_bypath_converted_to_uuid_in_stabilize_all_mode`
- Include docstrings explaining what the test validates
- Use pytest fixtures from `tests/conftest.py`

## 🏗️ Architecture

Key components:

- **hyper2kvm/orchestrator/**: Main pipeline orchestration
- **hyper2kvm/fixers/**: Guest OS fixes (offline and live)
- **hyper2kvm/vmware/**: vSphere integration (powered by hypersdk)
- **hyper2kvm/converters/**: Disk format conversion
- **hyper2kvm/testers/**: Boot testing (QEMU, libvirt)

See [01-Architecture.md](01-Architecture.md) for detailed architecture documentation.

## 🔐 Security

- **Never commit secrets** (passwords, API keys, tokens)
- Use `.gitignore` for sensitive files
- Report security issues privately to: ssahani@zyvor.dev
- See [SECURITY.md](../SECURITY.md) for our security policy

## 📖 Documentation

- **User guides**: `docs/*.md`
- **API documentation**: Python docstrings
- **Examples**: `examples/`

When adding features:
1. Update relevant docs in `docs/`
2. Add examples if applicable
3. Update README.md if it changes installation or quick start

## 🎨 Code Style

We use `ruff` for linting and formatting:

```bash
# Auto-format code
make fmt

# Check for issues
make lint

# Manual commands
ruff format hyper2kvm/
ruff check --fix hyper2kvm/
```

### Style Guidelines

- **Line length**: 120 characters (not 80)
- **Imports**: Sorted by ruff
- **Type hints**: Use modern syntax (`str | None` not `Optional[str]`)
- **Docstrings**: Use for public functions/classes
- **Comments**: Explain "why" not "what"

## 🤝 Community

- **GitHub Issues**: https://github.com/ssahani/hyper2kvm/issues
- **Discussions**: https://github.com/ssahani/hyper2kvm/discussions
- **Maintainer**: ZyvorAI Labs Private Limited (ssahani@zyvor.dev)

## 📜 License

hyper2kvm is licensed under **Proprietary (Zyvor AI Labs)**. By contributing, you agree that your contributions will be licensed under the same license.

See [LICENSE](../LICENSE) for the full license text.

---

## 🙏 Thank You!

Every contribution helps make hyper2kvm better for everyone. Whether it's code, documentation, bug reports, or feature requests - we appreciate your help!
