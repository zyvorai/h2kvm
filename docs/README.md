# hyper2kvm- Documentation

Enterprise VM migration — any hypervisor to KVM

## Start Here

| Goal | Document |
|------|----------|
| Quick start | [README.md#quick-start-](../README.md#quick-start-) |
| Kubernetes deploy | [README.md#kubernetes--openshift-deployment-️](../README.md#kubernetes--openshift-deployment-️) |
| Examples | [](../examples/) |
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
| **hypersdk / hyper2kvm** | VM migration |
| **guestkit** | Offline VM assurance |
| **packetwolf** | Network intelligence |
| **Aether** | Runtime portability |
| **hermes** | Application layer for K8s |

See also: [../README.md](../README.md)
