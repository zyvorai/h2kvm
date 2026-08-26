# Debian/Ubuntu Packaging for h2kvm

This directory contains the Debian packaging files for h2kvm.

## Building the Package

### Prerequisites

Install the required build dependencies:

```bash
# Debian/Ubuntu
sudo apt-get install debhelper-compat dh-python python3-all python3-setuptools \
                     python3-pip python3-build python3-sphinx \
                     python3-sphinx-rtd-theme devscripts
```

### Build Process

1. **Build source package:**

```bash
cd /path/to/h2kvm
debuild -us -uc -S
```

2. **Build binary package:**

```bash
cd /path/to/h2kvm
debuild -us -uc -b
```

Or use `dpkg-buildpackage`:

```bash
dpkg-buildpackage -us -uc -b
```

3. **Build with pbuilder (clean environment):**

```bash
sudo pbuilder create
sudo pbuilder build ../h2kvm_*.dsc
```

### Package Files

The built packages will be created in the parent directory:

- `h2kvm_0.2.1-1_all.deb` - Binary package
- `h2kvm_0.2.1-1.dsc` - Source package description
- `h2kvm_0.2.1-1.tar.xz` - Source tarball
- `h2kvm_0.2.1-1_amd64.buildinfo` - Build information
- `h2kvm_0.2.1-1_amd64.changes` - Changes file

## Installing the Package

```bash
sudo dpkg -i h2kvm_0.2.1-1_all.deb
sudo apt-get install -f  # Install dependencies if needed
```

## Testing the Package

### Lintian Checks

Run lintian to check for common packaging issues:

```bash
lintian ../h2kvm_0.2.1-1_all.deb
```

### Package Contents

List package contents:

```bash
dpkg -c ../h2kvm_0.2.1-1_all.deb
```

### Installation Test

Test installation in a clean container:

```bash
# Using Docker
docker run -it --rm -v $(pwd)/..:/packages debian:latest bash
apt-get update
apt-get install -y /packages/h2kvm_0.2.1-1_all.deb
h2kvm --version
```

## Packaging Files

- **control** - Package metadata and dependencies
- **changelog** - Version history
- **rules** - Build instructions
- **copyright** - Licensing information
- **install** - Additional files to install
- **dirs** - Directories to create
- **conffiles** - Configuration files to preserve
- **postinst** - Post-installation script
- **prerm** - Pre-removal script
- **postrm** - Post-removal script
- **h2kvm.service** - Main systemd service
- **h2kvm@.service** - Template systemd service
- **source/format** - Source package format
- **watch** - Upstream version tracking

## Uploading to PPA (Ubuntu)

1. **Set up GPG key and configure dput:**

```bash
# Create/import GPG key
gpg --gen-key

# Configure dput for Launchpad
cat > ~/.dput.cf << EOF
[ppa]
fqdn = ppa.launchpad.net
method = ftp
incoming = ~username/ubuntu/ppa/
login = anonymous
allow_unsigned_uploads = 0
EOF
```

2. **Build signed source package:**

```bash
debuild -S -k<YOUR_GPG_KEY_ID>
```

3. **Upload to PPA:**

```bash
dput ppa ../h2kvm_0.2.1-1_source.changes
```

## Contributing

When making changes to the packaging:

1. Update `debian/changelog` with your changes:
   ```bash
   dch -i  # Increment version
   dch -a  # Add entry to current version
   ```

2. Test the build locally before committing

3. Run lintian to check for issues

## Resources

- [Debian New Maintainers' Guide](https://www.debian.org/doc/manuals/maint-guide/)
- [Debian Python Policy](https://www.debian.org/doc/packaging-manuals/python-policy/)
- [Ubuntu Packaging Guide](https://packaging.ubuntu.com/html/)
- [Debhelper Documentation](https://manpages.debian.org/debhelper)
