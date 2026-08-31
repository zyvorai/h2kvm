# Security Policy

## Supported Versions

We provide security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.3.x   | :white_check_mark: |
| 0.2.x   | :white_check_mark: |
| < 0.2   | :x:                |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report them via one of the following methods:

### 1. GitHub Security Advisories (Preferred)

Report vulnerabilities through GitHub's private vulnerability reporting:

1. Go to https://github.com/ssahani/h2kvm/security/advisories
2. Click "Report a vulnerability"
3. Fill in the details

### 2. Email

Send an email to: **ssahani@zyvor.dev**

Include the following information:

- Type of vulnerability
- Full paths of affected source files
- Location of the affected source code (tag/branch/commit or direct URL)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue, including how an attacker might exploit it

### What to Expect

- **Response time**: Within 48 hours
- **Initial assessment**: Within 1 week
- **Fix timeline**: Critical issues within 2 weeks, others within 4 weeks
- **Disclosure**: Coordinated disclosure after fix is available

## Security Measures

h2kvm implements several security measures:

### Code Quality

- **Static Analysis**: Bandit security scanning in CI
- **Dependency Scanning**: Dependabot and pip-audit
- **Type Safety**: MyPy type checking
- **Code Review**: All changes reviewed before merge

### Runtime Security

- **Path Traversal Protection**: All file paths validated (see `h2kvm/vmware/utils/vmdk_parser.py`)
- **Command Injection Prevention**: No shell=True in subprocess calls
- **Input Validation**: All user inputs sanitized
- **TLS Verification**: Certificate validation enforced for VMware/Azure connections

### Specific Protections

1. **VMDK Parsing** (CVE-like vulnerabilities prevented):
   - Path traversal in extent paths blocked
   - Maximum file size limits enforced
   - Malicious descriptor detection
   - See: `tests/unit/test_vmware/test_vmdk_security.py`

2. **SSH/Remote Operations**:
   - Host key verification required
   - No password storage
   - Timeout enforcement

3. **Windows Registry Operations**:
   - Offline-only registry edits (via guestfs backend)
   - Backup before modifications
   - Validation after changes

## Security Best Practices for Users

### Production Usage

1. **Run with Least Privilege**
   ```bash
   # Don't run as root unless absolutely necessary
   sudo -u vmadmin h2kvm vsphere ...
   ```

2. **Network Security**
   ```bash
   # Use VPN/bastion for vSphere access
   # Verify TLS certificates
   h2kvm vsphere --verify-ssl ...
   ```

3. **Credential Management**
   ```bash
   # Use environment variables, not command-line args
   export VCENTER_PASSWORD="..."
   h2kvm vsphere --username admin

   # Or use credential files with restricted permissions
   chmod 600 ~/.h2kvm/credentials.yaml
   ```

4. **Audit Logging**
   ```bash
   # Enable detailed logging for audit trails
   h2kvm --log-level debug --log-file /var/log/h2kvm/migration.log ...
   ```

### Development

1. **Pre-commit Hooks**
   ```bash
   pip install pre-commit
   pre-commit install
   ```

2. **Security Scanning**
   ```bash
   make security
   # or
   hatch run security
   ```

3. **Dependency Updates**
   ```bash
   # Keep dependencies updated
   pip install --upgrade -r requirements.txt
   pip-audit
   ```

## Known Security Considerations

### 1. System Dependencies

h2kvm uses GuestKit by default (with `qemu-img` and `qemu-nbd`). These tools run with elevated privileges:

- **Risk**: Potential privilege escalation
- **Mitigation**: Only use trusted disk images, validate inputs
- **Status**: Inherent to offline VM manipulation

### 2. VMware API Credentials

Credentials must be provided for vSphere operations:

- **Risk**: Credential exposure
- **Mitigation**: Use environment variables, vault integration
- **Recommendation**: Implement OAuth/token-based auth (planned)

### 3. Windows Driver Injection

Offline Windows registry modification:

- **Risk**: VM corruption if interrupted
- **Mitigation**: Automatic backups, atomic operations
- **Status**: Production-ready with safeguards

## Security Testing

We perform regular security testing:

- **SAST**: Bandit, ruff security rules
- **Dependency Scanning**: pip-audit, Safety, Dependabot
- **Vulnerability Database**: CVE monitoring
- **Penetration Testing**: Community-driven (contributions welcome)

### Running Security Tests

```bash
# Full security scan
make security

# Generate security report
hatch run security-audit

# Dependency audit
pip-audit --desc

# Check for secrets
detect-secrets scan --baseline .secrets.baseline
```

## Hall of Fame

We recognize security researchers who responsibly disclose vulnerabilities:

<!-- Contributors will be listed here -->

## References

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [Python Security Guide](https://python.readthedocs.io/en/stable/library/security_warnings.html)

## Contact

For security inquiries: **ssahani@zyvor.dev**

For general support: https://github.com/ssahani/h2kvm/issues

---

*This security policy is reviewed quarterly and updated as needed.*

**Last Updated**: 2026-03-29
