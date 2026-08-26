# Security Features Setup

This document explains how to enable GitHub security features for this repository.

## Required Actions

Some security features require manual setup in the GitHub repository settings.

---

## 1. Enable Dependency Graph

**Required for:**
- Dependabot alerts
- Dependency review on PRs
- Security advisories

**Steps:**

1. Go to your repository settings:
   ```
   https://github.com/ssahani/hyper2kvm/settings/security_analysis
   ```

2. Under "Data services":
   - ✅ Enable **Dependency graph**

3. Under "Dependabot":
   - ✅ Enable **Dependabot alerts**
   - ✅ Enable **Dependabot security updates**

**Note:** These features are automatically enabled for public repositories but may need manual activation for private repos.

---

## 2. Configure Code Scanning

**Optional but recommended:**

1. Go to Security > Code scanning
   ```
   https://github.com/ssahani/hyper2kvm/security/code-scanning
   ```

2. Click "Set up code scanning"

3. Choose "CodeQL Analysis" (recommended)

4. Configure and commit the workflow

---

## 3. Enable Secret Scanning

**For public repositories:** Automatically enabled

**For private repositories:**

1. Go to Settings > Security & analysis

2. Enable:
   - ✅ **Secret scanning**
   - ✅ **Push protection** (prevents committing secrets)

---

## 4. Review Security Advisories

Periodically check for security advisories:

```
https://github.com/ssahani/hyper2kvm/security/advisories
```

---

## Current Security Workflow Status

### ✅ Always Working (No Setup Required)

These run automatically:

- **Bandit Security Scan** - Python security issue detection
- **pip-audit** - Known CVE detection in dependencies
- **Safety** - Python package vulnerability scanning

### ⚠️ Requires Setup

These require dependency graph to be enabled:

- **Dependency Review** - PR dependency change analysis
- **Dependabot Alerts** - Automatic vulnerability notifications
- **Dependabot Security Updates** - Automatic security patches

---

## Dependency Graph Not Available?

If you see:
```
Dependency review is not supported on this repository
```

**Possible reasons:**

1. **Private repository** - Feature may not be available on your plan
2. **Dependency graph disabled** - Enable in settings
3. **Repository too new** - Wait a few minutes after enabling

**Workaround:**

The workflow is configured to continue even if dependency review fails:

```yaml
continue-on-error: true
```

Security scanning (Bandit, pip-audit) will still work!

---

## Recommended Security Checklist

### For Public Repositories:

- [x] Dependency graph enabled (automatic)
- [x] Dependabot alerts enabled (automatic)
- [x] Secret scanning enabled (automatic)
- [x] Bandit security scans (via GitHub Actions)
- [x] pip-audit CVE checks (via GitHub Actions)
- [ ] Code scanning with CodeQL (optional)
- [ ] Branch protection rules
- [ ] Required reviews for PRs
- [ ] Status checks must pass

### For Private Repositories:

- [ ] Enable dependency graph (Settings > Security)
- [ ] Enable Dependabot alerts
- [ ] Enable secret scanning (if available)
- [x] Bandit security scans (via GitHub Actions)
- [x] pip-audit CVE checks (via GitHub Actions)
- [ ] Code scanning with CodeQL (if available)
- [ ] Branch protection rules
- [ ] Required reviews for PRs

---

## Enabling Branch Protection

Recommended settings for `main` branch:

1. Go to Settings > Branches

2. Add rule for `main`:
   - ✅ Require pull request before merging
   - ✅ Require approvals: 1
   - ✅ Require status checks to pass
   - ✅ Require branches to be up to date
   - Select required checks:
     - `test (3.12)` (at minimum)
     - `lint` (code quality)
     - `security` (security scan)
   - ✅ Require conversation resolution
   - ✅ Include administrators (optional)

---

## Security Scanning Results

### View Security Scan Results

After each push/PR:

1. Go to Actions tab
2. Click on the workflow run
3. Expand "Security Scanning" job
4. Review Bandit and pip-audit output

### Download Scan Reports

Security scan results are uploaded as artifacts:

1. Go to Actions > Select workflow run
2. Scroll to "Artifacts"
3. Download `bandit-results` (JSON format)

---

## Handling Security Alerts

### Dependabot Alerts

When Dependabot finds a vulnerability:

1. You'll receive an email notification
2. Check Security > Dependabot alerts
3. Review the vulnerability details
4. Dependabot may create a PR to fix it
5. Review and merge the PR

### Bandit Findings

When Bandit finds security issues:

1. Check the GitHub Actions log
2. Review the finding details
3. Assess if it's a real issue or false positive
4. Fix the code or add a `# nosec` comment if safe

### pip-audit Findings

When pip-audit finds CVEs:

1. Check which package is vulnerable
2. Update to a fixed version in `requirements.txt`
3. Test the update
4. Create a PR with the fix

---

## False Positives

### Bandit False Positives

If Bandit flags safe code:

```python
# This is safe because [reason]
password = os.environ.get("PASSWORD")  # nosec B105
```

### Dependabot False Positives

If a vulnerability doesn't apply:

1. Go to the alert
2. Click "Dismiss alert"
3. Choose reason (e.g., "Vulnerable code not used")

---

## Regular Security Maintenance

### Weekly Tasks

- [ ] Review Dependabot PRs
- [ ] Check for new security alerts
- [ ] Review failed security scans

### Monthly Tasks

- [ ] Review all dependencies for updates
- [ ] Check for deprecated packages
- [ ] Review security advisories
- [ ] Update security scanning tools

---

## External Security Resources

- [GitHub Security Best Practices](https://docs.github.com/en/code-security/getting-started/securing-your-repository)
- [Dependabot Documentation](https://docs.github.com/en/code-security/dependabot)
- [Python Security Guide](https://python.readthedocs.io/en/latest/library/security_warnings.html)
- [OWASP Python Security](https://owasp.org/www-project-python-security/)

---

## Need Help?

If you encounter issues with security features:

1. Check [GitHub Status](https://www.githubstatus.com/)
2. Review [GitHub Community Discussions](https://github.com/orgs/community/discussions)
3. Contact GitHub Support (for private repo issues)
4. Open an issue in this repository

---

## Summary

**Minimum setup for security:**

```bash
# 1. Enable in repository settings
Go to: Settings > Security & analysis
Enable: Dependency graph, Dependabot alerts

# 2. That's it! GitHub Actions handles the rest
```

**Security scans run automatically:**
- ✅ On every push to main
- ✅ On every pull request
- ✅ Weekly scheduled scans
- ✅ Dependabot weekly checks
