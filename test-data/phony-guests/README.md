# Phony Guest Images for Testing

Minimal disk images that fool the guestfs inspection API, used for
testing hyper2kvm's conversion pipeline without needing real OS installs.

## Images

| Image | Description | Size |
|-------|-------------|------|
| `fedora.img` | Minimal Fedora-like (ext4, GRUB2, fstab) | 256MB |
| `windows.img` | Minimal Windows-like (NTFS, registry hives) | 512MB |
| `windows-multi-disk-sda.img` | Blank data disk (NTFS) | 256MB |
| `windows-multi-disk-sdb.img` | Windows OS disk (boot on 2nd disk) | 512MB |
| `ubuntu.img` | Minimal Ubuntu-like (ext4, netplan) | 256MB |

## Building

```bash
# Build all phony guests (requires root for guestfs)
sudo python3 test-data/phony-guests/build_all.py

# Build a specific image
sudo python3 test-data/phony-guests/build_all.py --only fedora
```

## Usage in Tests

```python
import pytest
from pathlib import Path

PHONY_GUESTS = Path(__file__).parent.parent / "test-data" / "phony-guests"

@pytest.mark.skipif(
    not (PHONY_GUESTS / "fedora.img").exists(),
    reason="Phony guest images not built (run: sudo python3 test-data/phony-guests/build_all.py)"
)
def test_fedora_conversion():
    ...
```
