# hyper2kvm Presentation Materials

Quick reference documents for presentations and demos.

## Documents

### 📊 [Quick Comparison](quick-comparison.md)
**One-page overview** - Perfect for slides or quick demos
- Simple side-by-side comparison
- Visual workflow diagrams
- Quick command examples
- **Use for:** 5-minute presentations

### 🏗️ [Pipeline Architecture](pipeline-architecture.md)
**Complete pipeline explanation** - How hyper2kvm really works
- 7-stage pipeline flow (FETCH → VALIDATE)
- Detailed stage breakdowns with diagrams
- Data flow examples (RHEL 9 migration)
- Orchestrator coordination
- Recovery and checkpointing
- **Use for:** Architecture presentations, technical training

### 📈 [Daemon vs CLI Workflow](daemon-vs-cli-workflow.md)
**Mode comparison** - Complete operational overview
- Architecture diagrams
- Decision matrix
- Production deployment examples
- CLI vs Daemon execution
- **Use for:** Operations teams, deployment planning

## Viewing Diagrams

These documents use Mermaid diagrams. View them in:
- **GitHub**: Renders automatically
- **VS Code**: Install "Markdown Preview Mermaid Support" extension
- **Online**: Copy to https://mermaid.live/

## Quick Reference

### CLI Mode
```bash
hyper2kvm local --source vm.vmdk --output vm.qcow2
```
- Interactive, manual execution
- Single VM focus
- Development/testing

### Daemon Mode
```bash
systemctl start hyper2kvm.service
cp *.vmdk /var/lib/hyper2kvm/queue/
```
- Automated, continuous processing
- Batch operations
- Production deployments

## Presentation Tips

### For Different Audiences

**Executive/Business (5 minutes)**
→ Use `quick-comparison.md`
- Focus on automation value
- Show time savings (daemon mode)

**Technical/Architects (15-30 minutes)**
→ Use `pipeline-architecture.md`
- Explain 7-stage pipeline
- Show how fixes work offline
- Emphasize deterministic, repeatable process

**Operations/DevOps (10-15 minutes)**
→ Use `daemon-vs-cli-workflow.md`
- CLI for testing, daemon for production
- systemd integration
- Monitoring and troubleshooting

### Suggested Flow

1. **Start with** "What problem does it solve?" (Quick Comparison)
2. **Explain how** "The 7-stage pipeline" (Pipeline Architecture)
3. **Show deployment** "CLI and Daemon modes" (Daemon vs CLI)
4. **Demo** Live conversion with CLI, then drop file in daemon queue

### Key Messages

- **Pipeline-based architecture** = Reliable, repeatable migrations
- **Offline fixing** = Works on broken VMs, no runtime dependencies
- **Two modes** = Flexibility for dev and production
