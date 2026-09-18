<!-- Copyright (c) 2026 ZyvorAI Labs Private Limited. -->
<!-- SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial -->

# Developer Certificate of Origin (DCO)

h2kvm uses the Developer Certificate of Origin (DCO) for inbound contributions,
in addition to the [Contributor License Agreement](CLA.md) required for
dual-licensing under AGPL-3.0 and the h2kvm Commercial License.

By making a contribution to this project, you certify that:

```
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.


Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

## How to sign off

Append a `Signed-off-by` line to every commit message using your real name and
email (matches `git config user.name` / `user.email`):

```
git commit -s -m "Your commit message"
```

Example trailer:

```
Signed-off-by: Jane Developer <jane@example.com>
```

PRs without DCO sign-off on each commit will not be merged.
