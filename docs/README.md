# h2kvm — Documentation

Enterprise VM migration — any hypervisor to KVM

## Start Here

| Goal | Document |
|------|----------|
| Quick start | [README.md#60-second-quick-start](../README.md#60-second-quick-start) |
| **Remote lab deploy** | [deployment/deploy-remote.md](deployment/deploy-remote.md) |
| **GuestKit integration** | [architecture/GUESTKIT.md](architecture/GUESTKIT.md) |
| Kubernetes deploy | [deployment/README.md](deployment/README.md) |
| Examples | [../examples/](../examples/) |
| **User journeys & acceptance criteria** | [User Stories](USER_STORIES.md) |

## User Stories

Persona-based journeys with acceptance criteria: **[USER_STORIES.md](USER_STORIES.md)**

| Persona | Focus |
|---------|-------|
| Alex (Migration Engineer) | VMware/Hyper-V to KVM pipelines |
| Morgan (Windows Admin) | Win10/11 migration with driver fixes |
| Jordan (K8s Platform) | Libvirt-to-KubeVirt migration |

## Ecosystem

Part of the [Zyvor / HyperSDK platform stack](https://zyvor.dev):

| Product | Role |
|---------|------|
| **hypercluster** | Kubernetes bootstrap |
| **machina** | Bare-metal hypervisor OS |
| **zeus-os (v9s)** | Cloud / KubeVirt control plane |
| **forge** | AI infrastructure on K8s |
| **h2kvm** | VM conversion + deploy (this repo's pipeline partner) |
| **guestkit** | Offline VM assurance (`hypersdk-guestkit`) |
| **packetwolf** | Network intelligence |
| **Aether** | Runtime portability |
| **hermes** | Application layer for K8s |

See also: [../README.md](../README.md)
