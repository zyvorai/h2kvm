# Enterprise Tutorial: Production Deployment at Scale

**Duration**: 4-8 hours
**Difficulty**: Expert
**Prerequisites**: Advanced tutorial completed, enterprise infrastructure access, automation experience

---

## What You'll Learn

By the end of this tutorial, you will:
- ✅ Deploy h2kvm in enterprise production environments
- ✅ Implement automated migration pipelines with CI/CD
- ✅ Configure centralized logging and monitoring
- ✅ Set up high-availability migration infrastructure
- ✅ Implement security best practices and compliance
- ✅ Manage migrations at scale (100+ VMs)
- ✅ Integrate with enterprise management tools (Ansible, Terraform)

---

## Prerequisites

### Infrastructure Requirements
- **Orchestration**: Ansible 2.10+, Terraform 1.0+, or equivalent
- **CI/CD**: Jenkins, GitLab CI, GitHub Actions, or similar
- **Monitoring**: Prometheus/Grafana or ELK stack
- **Storage**: Enterprise SAN/NAS with sufficient capacity
- **Networking**: Dedicated migration VLANs, 10GbE+ recommended

### Knowledge Requirements
- Linux system administration at scale
- Infrastructure as Code (IaC) concepts
- CI/CD pipeline design
- Enterprise security practices
- Backup and disaster recovery procedures

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                  Enterprise Migration Platform              │
└─────────────────────────────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐    ┌──────────────┐    ┌──────────────┐
│  CI/CD        │    │  Migration   │    │  Monitoring  │
│  Pipeline     │────│  Workers     │────│  & Alerts    │
│  (GitLab CI)  │    │  (h2kvmctl)  │    │ (Prometheus) │
└───────────────┘    └──────────────┘    └──────────────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐    ┌──────────────┐    ┌──────────────┐
│  Artifact     │    │  Centralized │    │  Compliance  │
│  Repository   │    │  Logging     │    │  Auditing    │
└───────────────┘    └──────────────┘    └──────────────┘
```

---

## Part 1: Ansible Automation

### 1.1: Ansible Inventory Setup

Create `inventory/production.yml`:

```yaml
all:
  children:
    migration_controllers:
      hosts:
        migration-controller-01:
          ansible_host: 10.0.1.10
        migration-controller-02:
          ansible_host: 10.0.1.11

    source_infrastructure:
      children:
        vmware_esxi:
          hosts:
            esxi-01.corp.local:
              ansible_host: 10.0.2.10
            esxi-02.corp.local:
              ansible_host: 10.0.2.11

    target_infrastructure:
      children:
        kvm_hosts:
          hosts:
            kvm-host-01:
              ansible_host: 10.0.3.10
            kvm-host-02:
              ansible_host: 10.0.3.11

  vars:
    ansible_user: ansible
    ansible_python_interpreter: /usr/bin/python3
    migration_base_dir: /opt/h2kvm
    migration_data_dir: /data/migrations
```

### 1.2: Ansible Playbook - Install h2kvm

Create `playbooks/install-h2kvm.yml`:

```yaml
---
- name: Install and configure h2kvm on migration controllers
  hosts: migration_controllers
  become: yes
  vars:
    h2kvm_version: "1.0.0"
    python_version: "3.10"

  tasks:
    - name: Install system dependencies
      package:
        name:
          - python3
          - python3-pip
          - qemu-img
          - qemu-system-x86
          - libvirt
          - ntfs-3g
          - libhivex-bin
        state: present

    - name: Create h2kvm user
      user:
        name: h2kvm
        system: yes
        create_home: yes
        home: /opt/h2kvm
        shell: /bin/bash

    - name: Create directory structure
      file:
        path: "{{ item }}"
        state: directory
        owner: h2kvm
        group: h2kvm
        mode: '0755'
      loop:
        - /opt/h2kvm/configs
        - /opt/h2kvm/logs
        - /opt/h2kvm/scripts
        - /data/migrations/incoming
        - /data/migrations/output
        - /data/migrations/work

    - name: Install h2kvm via pip
      pip:
        name: "h2kvm[full]=={{ h2kvm_version }}"
        state: present
        executable: pip3

    - name: Verify installation
      command: h2kvmctl --version
      register: version_output
      changed_when: false

    - name: Display version
      debug:
        msg: "Installed {{ version_output.stdout }}"

    - name: Copy SSH keys for ESXi access
      copy:
        src: "{{ item.src }}"
        dest: "{{ item.dest }}"
        owner: h2kvm
        group: h2kvm
        mode: '0600'
      loop:
        - { src: 'files/esxi_id_rsa', dest: '/opt/h2kvm/.ssh/id_rsa' }
        - { src: 'files/esxi_id_rsa.pub', dest: '/opt/h2kvm/.ssh/id_rsa.pub' }

    - name: Configure sudoers for h2kvm user
      copy:
        dest: /etc/sudoers.d/h2kvm
        content: |
          # Allow h2kvm user to run migration commands
          h2kvm ALL=(ALL) NOPASSWD: /usr/bin/qemu-img
          h2kvm ALL=(ALL) NOPASSWD: /usr/bin/qemu-nbd
          h2kvm ALL=(ALL) NOPASSWD: /usr/bin/mount
          h2kvm ALL=(ALL) NOPASSWD: /usr/bin/umount
          h2kvm ALL=(ALL) NOPASSWD: /usr/bin/blkid
          h2kvm ALL=(ALL) NOPASSWD: /usr/bin/virsh
        mode: '0440'
        validate: 'visudo -cf %s'

    - name: Install monitoring agent (node_exporter)
      include_role:
        name: prometheus.prometheus.node_exporter
```

### 1.3: Ansible Playbook - Execute Migrations

Create `playbooks/execute-migration.yml`:

```yaml
---
- name: Execute VM migration using h2kvm
  hosts: migration_controllers[0]
  become: yes
  become_user: h2kvm
  vars:
    vm_name: "{{ vm_to_migrate }}"
    migration_config: "/opt/h2kvm/configs/{{ vm_name }}.yaml"

  tasks:
    - name: Validate migration config exists
      stat:
        path: "{{ migration_config }}"
      register: config_stat
      failed_when: not config_stat.stat.exists

    - name: Create migration log directory
      file:
        path: "/opt/h2kvm/logs/{{ vm_name }}"
        state: directory
        mode: '0755'

    - name: Execute migration
      command: >
        h2kvmctl --config {{ migration_config }}
      register: migration_result
      environment:
        MIGRATION_LOG: "/opt/h2kvm/logs/{{ vm_name }}/migration.log"

    - name: Check migration status
      debug:
        msg: "Migration {{ 'succeeded' if migration_result.rc == 0 else 'failed' }}"

    - name: Upload migration report to artifact repository
      synchronize:
        src: "/data/migrations/output/{{ vm_name }}/migration-report.md"
        dest: "{{ artifact_repo_url }}/{{ vm_name }}/{{ ansible_date_time.date }}/"
      when: migration_result.rc == 0

    - name: Send notification (success)
      uri:
        url: "{{ slack_webhook_url }}"
        method: POST
        body_format: json
        body:
          text: "✅ Migration succeeded for {{ vm_name }}"
      when: migration_result.rc == 0

    - name: Send notification (failure)
      uri:
        url: "{{ slack_webhook_url }}"
        method: POST
        body_format: json
        body:
          text: "💥 Migration failed for {{ vm_name }}"
      when: migration_result.rc != 0

    - name: Fail playbook if migration failed
      fail:
        msg: "Migration failed for {{ vm_name }}"
      when: migration_result.rc != 0
```

### 1.4: Run Ansible Playbook

```bash
# Install h2kvm on all migration controllers
ansible-playbook -i inventory/production.yml playbooks/install-h2kvm.yml

# Execute migration for specific VM
ansible-playbook -i inventory/production.yml playbooks/execute-migration.yml \
  -e vm_to_migrate=web-server-01 \
  -e slack_webhook_url=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Execute batch migration
for vm in web-{01..10}; do
  ansible-playbook -i inventory/production.yml playbooks/execute-migration.yml \
    -e vm_to_migrate=$vm
done
```

---

## Part 2: CI/CD Pipeline Integration

### 2.1: GitLab CI Pipeline

Create `.gitlab-ci.yml`:

```yaml
stages:
  - validate
  - migrate
  - test
  - deploy
  - cleanup

variables:
  MIGRATION_BASE: "/data/migrations"
  ARTIFACT_RETENTION: "30 days"

# Validate migration configuration
validate:config:
  stage: validate
  image: python:3.10
  script:
    - pip install h2kvm[full]
    - h2kvmctl --config migrations/${VM_NAME}.yaml --dump-config
    - h2kvmctl --config migrations/${VM_NAME}.yaml --dry-run
  only:
    changes:
      - migrations/*.yaml

# Execute migration
migrate:vm:
  stage: migrate
  tags:
    - migration-controller
  script:
    - h2kvmctl --config migrations/${VM_NAME}.yaml
  artifacts:
    paths:
      - output/${VM_NAME}/migration-report.*
      - output/${VM_NAME}/*.qcow2
    expire_in: $ARTIFACT_RETENTION
  only:
    variables:
      - $MIGRATION_TRIGGER == "true"

# Automated testing
test:boot:
  stage: test
  tags:
    - kvm-test-host
  script:
    - virsh define output/${VM_NAME}/${VM_NAME}.xml
    - virsh start ${VM_NAME}
    - sleep 60
    - virsh dominfo ${VM_NAME} | grep "State.*running"
  after_script:
    - virsh destroy ${VM_NAME} || true
    - virsh undefine ${VM_NAME} || true
  dependencies:
    - migrate:vm

# Deploy to production
deploy:production:
  stage: deploy
  tags:
    - kvm-prod-host
  script:
    - virsh define output/${VM_NAME}/${VM_NAME}.xml
    - virsh start ${VM_NAME}
    - virsh autostart ${VM_NAME}
  when: manual
  only:
    - main
  dependencies:
    - test:boot

# Cleanup old artifacts
cleanup:artifacts:
  stage: cleanup
  script:
    - find $MIGRATION_BASE/output -type f -mtime +30 -delete
  only:
    - schedules
```

### 2.2: GitHub Actions Workflow

Create `.github/workflows/vm-migration.yml`:

```yaml
name: VM Migration Pipeline

on:
  workflow_dispatch:
    inputs:
      vm_name:
        description: 'VM name to migrate'
        required: true
      environment:
        description: 'Target environment'
        required: true
        type: choice
        options:
          - development
          - staging
          - production

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install h2kvm
        run: |
          pip install h2kvm[full]

      - name: Validate configuration
        run: |
          h2kvmctl --config configs/${{ github.event.inputs.vm_name }}.yaml --dump-config
          h2kvmctl --config configs/${{ github.event.inputs.vm_name }}.yaml --dry-run

  migrate:
    needs: validate
    runs-on: [self-hosted, migration-controller]
    steps:
      - uses: actions/checkout@v3

      - name: Execute migration
        run: |
          h2kvmctl --config configs/${{ github.event.inputs.vm_name }}.yaml

      - name: Upload migration artifacts
        uses: actions/upload-artifact@v3
        with:
          name: migration-report-${{ github.event.inputs.vm_name }}
          path: |
            output/${{ github.event.inputs.vm_name }}/migration-report.*
          retention-days: 30

  test:
    needs: migrate
    runs-on: [self-hosted, kvm-test]
    if: github.event.inputs.environment != 'production'
    steps:
      - name: Boot test
        run: |
          virsh define output/${{ github.event.inputs.vm_name }}/${{ github.event.inputs.vm_name }}.xml
          virsh start ${{ github.event.inputs.vm_name }}
          sleep 60
          virsh dominfo ${{ github.event.inputs.vm_name }} | grep "State.*running"

      - name: Cleanup
        if: always()
        run: |
          virsh destroy ${{ github.event.inputs.vm_name }} || true
          virsh undefine ${{ github.event.inputs.vm_name }} || true

  deploy:
    needs: [migrate, test]
    runs-on: [self-hosted, kvm-${{ github.event.inputs.environment }}]
    environment: ${{ github.event.inputs.environment }}
    steps:
      - name: Deploy VM
        run: |
          virsh define output/${{ github.event.inputs.vm_name }}/${{ github.event.inputs.vm_name }}.xml
          virsh start ${{ github.event.inputs.vm_name }}
          virsh autostart ${{ github.event.inputs.vm_name }}

      - name: Notify Slack
        uses: slackapi/slack-github-action@v1
        with:
          payload: |
            {
              "text": "✅ VM ${{ github.event.inputs.vm_name }} migrated to ${{ github.event.inputs.environment }}"
            }
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
```

---

## Part 3: Monitoring and Observability

### 3.1: Prometheus Metrics Exporter

Create `scripts/migration-metrics-exporter.py`:

```python
#!/usr/bin/env python3
"""
Prometheus metrics exporter for h2kvm migrations.
Exposes migration statistics as Prometheus metrics.
"""

from prometheus_client import start_http_server, Gauge, Counter, Histogram
import json
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Define metrics
migration_duration = Histogram(
    'h2kvm_migration_duration_seconds',
    'Time spent migrating VM',
    ['vm_name', 'source_format']
)

migration_size = Gauge(
    'h2kvm_migration_size_bytes',
    'Size of migrated VM in bytes',
    ['vm_name']
)

migration_success = Counter(
    'h2kvm_migrations_total',
    'Total number of migrations',
    ['vm_name', 'status']
)

migration_speed = Gauge(
    'h2kvm_migration_speed_mbps',
    'Average migration speed in MB/s',
    ['vm_name']
)

class MigrationReportHandler(FileSystemEventHandler):
    """Watch for new migration reports and export metrics."""

    def on_created(self, event):
        if event.src_path.endswith('migration-report.json'):
            self.process_report(event.src_path)

    def process_report(self, report_path):
        """Parse migration report and update metrics."""
        try:
            with open(report_path) as f:
                report = json.load(f)

            vm_name = report.get('vm_name', 'unknown')
            source_format = report.get('source_format', 'unknown')
            duration = report.get('migration_duration_seconds', 0)
            size_bytes = report.get('output_size_bytes', 0)
            status = 'success' if report.get('success') else 'failure'

            # Update metrics
            migration_duration.labels(
                vm_name=vm_name,
                source_format=source_format
            ).observe(duration)

            migration_size.labels(vm_name=vm_name).set(size_bytes)

            migration_success.labels(
                vm_name=vm_name,
                status=status
            ).inc()

            if duration > 0 and size_bytes > 0:
                speed_mbps = (size_bytes / (1024 * 1024)) / duration
                migration_speed.labels(vm_name=vm_name).set(speed_mbps)

            print(f"✅ Exported metrics for {vm_name}")

        except Exception as e:
            print(f"Error processing {report_path}: {e}")

if __name__ == '__main__':
    # Start Prometheus HTTP server
    start_http_server(9090)
    print("Metrics exporter started on :9090")

    # Watch migration output directory
    output_dir = Path('/data/migrations/output')
    event_handler = MigrationReportHandler()
    observer = Observer()
    observer.schedule(event_handler, str(output_dir), recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
```

### 3.2: Prometheus Configuration

Create `prometheus/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  # Migration metrics exporter
  - job_name: 'h2kvm-migrations'
    static_configs:
      - targets: ['migration-controller-01:9090', 'migration-controller-02:9090']

  # Node exporter for migration controllers
  - job_name: 'migration-controllers'
    static_configs:
      - targets: ['migration-controller-01:9100', 'migration-controller-02:9100']

  # KVM host metrics
  - job_name: 'kvm-hosts'
    static_configs:
      - targets: ['kvm-host-01:9100', 'kvm-host-02:9100']

# Alerting rules
rule_files:
  - 'alerts/migration-alerts.yml'

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']
```

### 3.3: Grafana Dashboard

Create `grafana/dashboards/h2kvm-migrations.json`:

```json
{
  "dashboard": {
    "title": "H2KVM Migration Dashboard",
    "panels": [
      {
        "title": "Migration Success Rate",
        "targets": [
          {
            "expr": "rate(h2kvm_migrations_total{status=\"success\"}[5m]) / rate(h2kvm_migrations_total[5m]) * 100"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Average Migration Speed",
        "targets": [
          {
            "expr": "avg(h2kvm_migration_speed_mbps)"
          }
        ],
        "type": "stat"
      },
      {
        "title": "Migration Duration by VM",
        "targets": [
          {
            "expr": "h2kvm_migration_duration_seconds"
          }
        ],
        "type": "heatmap"
      },
      {
        "title": "Total Data Migrated",
        "targets": [
          {
            "expr": "sum(h2kvm_migration_size_bytes) / 1024 / 1024 / 1024"
          }
        ],
        "type": "stat",
        "unit": "GB"
      }
    ]
  }
}
```

### 3.4: Alert Rules

Create `prometheus/alerts/migration-alerts.yml`:

```yaml
groups:
  - name: migration_alerts
    interval: 30s
    rules:
      - alert: MigrationFailureRate
        expr: |
          (
            rate(h2kvm_migrations_total{status="failure"}[10m])
            /
            rate(h2kvm_migrations_total[10m])
          ) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High migration failure rate"
          description: "Migration failure rate is {{ $value | humanizePercentage }} (threshold: 10%)"

      - alert: MigrationSlowSpeed
        expr: h2kvm_migration_speed_mbps < 50
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Slow migration speed for {{ $labels.vm_name }}"
          description: "Migration speed is {{ $value }} MB/s (threshold: 50 MB/s)"

      - alert: MigrationControllerDown
        expr: up{job="h2kvm-migrations"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Migration controller is down"
          description: "Migration controller {{ $labels.instance }} is unreachable"
```

---

## Part 4: Security and Compliance

### 4.1: Encryption at Rest

Create `scripts/encrypt-migration-output.sh`:

```bash
#!/bin/bash
# Encrypt migrated VMs using LUKS

VM_NAME="$1"
OUTPUT_DIR="/data/migrations/output/${VM_NAME}"
ENCRYPTED_DIR="/data/migrations/encrypted/${VM_NAME}"

mkdir -p "$ENCRYPTED_DIR"

# Get encryption key from vault
ENCRYPTION_KEY=$(vault kv get -field=key secret/migration-encryption)

# Encrypt qcow2 image
qemu-img convert -O qcow2 \
  --object secret,id=sec0,data="$ENCRYPTION_KEY" \
  --image-opts driver=qcow2,encrypt.format=luks,encrypt.key-secret=sec0 \
  "${OUTPUT_DIR}/${VM_NAME}.qcow2" \
  "${ENCRYPTED_DIR}/${VM_NAME}-encrypted.qcow2"

# Calculate and store checksum
sha256sum "${ENCRYPTED_DIR}/${VM_NAME}-encrypted.qcow2" > \
  "${ENCRYPTED_DIR}/${VM_NAME}-encrypted.qcow2.sha256"

echo "✅ VM encrypted and stored at ${ENCRYPTED_DIR}"
```

### 4.2: Audit Logging

Create `scripts/audit-log.sh`:

```bash
#!/bin/bash
# Centralized audit logging for migrations

AUDIT_LOG="/var/log/h2kvm/audit.log"
SYSLOG_SERVER="syslog.corp.local:514"

log_audit_event() {
    local event_type="$1"
    local vm_name="$2"
    local user="$3"
    local result="$4"
    local details="$5"

    # Log locally
    echo "$(date -Iseconds) | $event_type | $vm_name | $user | $result | $details" >> "$AUDIT_LOG"

    # Send to syslog server
    logger -n "$SYSLOG_SERVER" -P 514 -t h2kvm-audit \
      "event=$event_type vm=$vm_name user=$user result=$result details=$details"

    # Send to SIEM (example: Splunk HEC)
    curl -k "https://splunk.corp.local:8088/services/collector" \
      -H "Authorization: Splunk ${SPLUNK_HEC_TOKEN}" \
      -d "{
        \"event\": {
          \"timestamp\": \"$(date -Iseconds)\",
          \"type\": \"$event_type\",
          \"vm_name\": \"$vm_name\",
          \"user\": \"$user\",
          \"result\": \"$result\",
          \"details\": \"$details\"
        }
      }"
}

# Example usage in migration scripts
log_audit_event "MIGRATION_START" "$VM_NAME" "$USER" "INITIATED" "Starting migration"
# ... run migration ...
log_audit_event "MIGRATION_END" "$VM_NAME" "$USER" "SUCCESS" "Migration completed"
```

### 4.3: Compliance Reporting

Create `scripts/compliance-report.py`:

```python
#!/usr/bin/env python3
"""
Generate compliance report for migrations.
Tracks encryption, audit trail, and data retention.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

def generate_compliance_report(days=30):
    """Generate compliance report for last N days."""

    report = {
        "report_date": datetime.now().isoformat(),
        "period_days": days,
        "metrics": {
            "total_migrations": 0,
            "encrypted_migrations": 0,
            "audit_logs_complete": 0,
            "retention_policy_compliant": 0
        },
        "violations": []
    }

    # Check all migrations in last N days
    cutoff_date = datetime.now() - timedelta(days=days)
    migrations_dir = Path("/data/migrations/output")

    for vm_dir in migrations_dir.iterdir():
        if not vm_dir.is_dir():
            continue

        report_file = vm_dir / "migration-report.json"
        if not report_file.exists():
            continue

        with open(report_file) as f:
            migration_data = json.load(f)

        migration_date = datetime.fromisoformat(
            migration_data.get("timestamp", "1970-01-01")
        )

        if migration_date < cutoff_date:
            continue

        report["metrics"]["total_migrations"] += 1

        # Check encryption
        encrypted_file = Path(f"/data/migrations/encrypted/{vm_dir.name}")
        if encrypted_file.exists():
            report["metrics"]["encrypted_migrations"] += 1
        else:
            report["violations"].append({
                "vm": vm_dir.name,
                "type": "ENCRYPTION_MISSING",
                "severity": "HIGH"
            })

        # Check audit logs
        # ... audit log verification logic ...

        # Check retention compliance
        # ... retention policy verification ...

    # Calculate compliance percentage
    if report["metrics"]["total_migrations"] > 0:
        encryption_rate = (
            report["metrics"]["encrypted_migrations"]
            / report["metrics"]["total_migrations"]
        ) * 100
        report["compliance_percentage"] = encryption_rate
    else:
        report["compliance_percentage"] = 100.0

    # Write report
    report_path = f"/var/log/h2kvm/compliance-report-{datetime.now().strftime('%Y%m%d')}.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"✅ Compliance report generated: {report_path}")
    print(f"Compliance rate: {report['compliance_percentage']:.2f}%")

    return report

if __name__ == '__main__':
    generate_compliance_report(days=30)
```

---

## Part 5: High Availability Setup

### 5.1: Load Balancer Configuration

Create HAProxy configuration for migration controllers:

```haproxy
# /etc/haproxy/haproxy.cfg

global
    log /dev/log local0
    maxconn 4096

defaults
    log global
    mode tcp
    option tcplog
    timeout connect 5000ms
    timeout client 50000ms
    timeout server 50000ms

frontend migration_api
    bind *:8443
    default_backend migration_controllers

backend migration_controllers
    balance roundrobin
    option httpchk GET /health
    server controller-01 10.0.1.10:8443 check
    server controller-02 10.0.1.11:8443 check

frontend metrics_export
    bind *:9090
    default_backend metrics_exporters

backend metrics_exporters
    balance roundrobin
    server exporter-01 10.0.1.10:9090 check
    server exporter-02 10.0.1.11:9090 check
```

### 5.2: Shared Storage Setup

Configure GlusterFS for shared migration storage:

```bash
# On all migration controllers
apt-get install -y glusterfs-server

# On controller-01
gluster peer probe migration-controller-02

gluster volume create migration-storage replica 2 \
  migration-controller-01:/data/gluster/migration \
  migration-controller-02:/data/gluster/migration

gluster volume start migration-storage

# Mount on all controllers
mount -t glusterfs localhost:/migration-storage /data/migrations
```

---

## Part 6: Disaster Recovery

### 6.1: Backup Migration Infrastructure

Create `scripts/backup-infrastructure.sh`:

```bash
#!/bin/bash
# Backup migration infrastructure configuration

BACKUP_DIR="/backups/h2kvm/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# Backup configurations
tar czf "$BACKUP_DIR/configs.tar.gz" /opt/h2kvm/configs/

# Backup scripts
tar czf "$BACKUP_DIR/scripts.tar.gz" /opt/h2kvm/scripts/

# Backup database (migration metadata)
sqlite3 /opt/h2kvm/migration.db ".backup $BACKUP_DIR/migration.db"

# Backup Ansible inventory and playbooks
tar czf "$BACKUP_DIR/ansible.tar.gz" /etc/ansible/

# Upload to S3
aws s3 sync "$BACKUP_DIR" s3://corp-backups/h2kvm/

echo "✅ Infrastructure backup completed"
```

### 6.2: Test Disaster Recovery

```bash
#!/bin/bash
# Test DR recovery procedure

# Simulate controller failure
systemctl stop h2kvm-daemon

# Restore from backup
LATEST_BACKUP=$(aws s3 ls s3://corp-backups/h2kvm/ | tail -1 | awk '{print $2}')
aws s3 sync "s3://corp-backups/h2kvm/$LATEST_BACKUP" /tmp/restore/

# Restore configurations
tar xzf /tmp/restore/configs.tar.gz -C /
tar xzf /tmp/restore/scripts.tar.gz -C /

# Restore database
sqlite3 /opt/h2kvm/migration.db < /tmp/restore/migration.db

# Restart services
systemctl start h2kvm-daemon

# Verify
h2kvmctl --version
```

---

## Summary

You've learned to:
- ✅ Deploy h2kvm at enterprise scale
- ✅ Integrate with CI/CD pipelines (GitLab, GitHub Actions)
- ✅ Automate with Ansible
- ✅ Implement comprehensive monitoring
- ✅ Ensure security and compliance
- ✅ Configure high availability
- ✅ Plan disaster recovery

## Production Checklist

```markdown
# Enterprise Deployment Checklist

## Infrastructure
- [ ] Migration controllers deployed (HA)
- [ ] Shared storage configured
- [ ] Network VLANs configured
- [ ] Load balancer deployed

## Automation
- [ ] Ansible playbooks tested
- [ ] CI/CD pipelines validated
- [ ] Artifact repository configured
- [ ] Notification integrations working

## Monitoring
- [ ] Prometheus metrics exporting
- [ ] Grafana dashboards created
- [ ] Alert rules configured
- [ ] On-call rotation defined

## Security
- [ ] Encryption at rest enabled
- [ ] Audit logging configured
- [ ] Compliance reporting automated
- [ ] Access controls implemented

## Operations
- [ ] Runbooks documented
- [ ] DR procedures tested
- [ ] Backup automation configured
- [ ] Team training completed
```

## Additional Resources

- [Ansible Galaxy Roles](https://galaxy.ansible.com/)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/)
- [GitLab CI Documentation](https://docs.gitlab.com/ee/ci/)
- [Terraform Registry](https://registry.terraform.io/)

---

**Enterprise Support Available**
- Custom integration consulting
- SLA-backed support
- Professional services for large-scale deployments

Contact: [enterprise@h2kvm.example.com](mailto:enterprise@h2kvm.example.com)
