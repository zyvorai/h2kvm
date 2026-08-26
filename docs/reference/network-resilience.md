# Network Resilience and Failure Handling

## Current Implementation

hyper2kvm implements connection retry with exponential backoff for VMware vSphere/vCenter connections:

### Retry Strategy
- **Max retries**: 3 (configurable via `vc_connection_max_retries`)
- **Backoff**: Exponential (2s, 4s, 8s, 16s...)
- **Jitter**: ±25% randomization to prevent thundering herd
- **Error classification**: Transient vs permanent errors

### Transient Errors (Will Retry)
- Connection timeouts
- Connection refused
- DNS resolution failures
- Network unreachable
- SSL handshake failures
- Connection reset by peer

### Permanent Errors (Fail Immediately)
- Authentication failures
- Authorization errors
- Invalid credentials

## Advanced: Netlink-Based Network Monitoring

For production deployments that need to handle extended network outages, you can use **Python netlink** (pyroute2) for real-time network state monitoring:

### Why Netlink?
- **Real-time**: Kernel notifies about network state changes immediately
- **Efficient**: No polling required
- **Reliable**: Direct kernel communication
- **Comprehensive**: Link up/down, IP changes, route changes

### Implementation Example

```python
#!/usr/bin/env python3
"""
Network-aware hyper2kvm wrapper with netlink monitoring.
Pauses operations during network outages and resumes when connectivity returns.
"""
import sys
import time
import logging
from threading import Thread, Event
try:
    from pyroute2 import IPRoute, IPDB
    NETLINK_AVAILABLE = True
except ImportError:
    NETLINK_AVAILABLE = False
    print("Warning: pyroute2 not available. Install: pip install pyroute2")

class NetworkMonitor:
    """
    Monitor network state using netlink and pause/resume operations.
    """
    def __init__(self, logger=None, required_interfaces=None):
        self.logger = logger or logging.getLogger(__name__)
        self.required_interfaces = required_interfaces or []  # e.g., ['eth0', 'ens192']
        self.network_up = Event()
        self.network_up.set()  # Assume up initially
        self._stop = Event()
        self._monitor_thread = None

    def start(self):
        """Start network monitoring thread"""
        if not NETLINK_AVAILABLE:
            self.logger.warning("Netlink not available, network monitoring disabled")
            return

        self._monitor_thread = Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        self.logger.info("Network monitor started")

    def stop(self):
        """Stop network monitoring"""
        self._stop.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)

    def _monitor_loop(self):
        """Main monitoring loop using netlink"""
        try:
            with IPRoute() as ipr:
                # Subscribe to link state changes
                ipr.bind()

                # Initial state check
                self._check_network_state(ipr)

                # Monitor for changes
                for msg in ipr.get_links():
                    if self._stop.is_set():
                        break

                    self._handle_link_event(ipr, msg)

        except Exception as e:
            self.logger.error(f"Network monitor error: {e}")

    def _check_network_state(self, ipr):
        """Check current network state"""
        has_connectivity = False

        try:
            links = ipr.get_links()

            for link in links:
                ifname = link.get_attr('IFLA_IFNAME')
                operstate = link.get_attr('IFLA_OPERSTATE')

                # Check if interface is up and running
                if operstate == 'UP':
                    if not self.required_interfaces or ifname in self.required_interfaces:
                        has_connectivity = True
                        break

        except Exception as e:
            self.logger.error(f"Error checking network state: {e}")

        if has_connectivity:
            if not self.network_up.is_set():
                self.logger.info("Network connectivity restored")
                self.network_up.set()
        else:
            if self.network_up.is_set():
                self.logger.warning("Network connectivity lost")
                self.network_up.clear()

    def _handle_link_event(self, ipr, msg):
        """Handle netlink link event"""
        ifname = msg.get_attr('IFLA_IFNAME')
        operstate = msg.get_attr('IFLA_OPERSTATE')

        if not self.required_interfaces or ifname in self.required_interfaces:
            if operstate == 'UP':
                self.logger.info(f"Interface {ifname} is UP")
                self.network_up.set()
            elif operstate == 'DOWN':
                self.logger.warning(f"Interface {ifname} is DOWN")
                self.network_up.clear()

    def wait_for_network(self, timeout=None):
        """
        Wait for network to be available.
        Returns True if network is available, False on timeout.
        """
        if self.network_up.wait(timeout=timeout):
            return True
        return False


class NetworkAwareVMwareClient:
    """
    VMware client wrapper that pauses operations during network outages.
    """
    def __init__(self, vmware_client, network_monitor):
        self.client = vmware_client
        self.monitor = network_monitor

    def connect_with_network_awareness(self):
        """Connect to vCenter with network state awareness"""
        max_network_wait = 300  # 5 minutes

        while True:
            # Wait for network to be available
            if not self.monitor.network_up.is_set():
                self.client.logger.warning(
                    "Network is down, waiting for connectivity..."
                )
                if not self.monitor.wait_for_network(timeout=max_network_wait):
                    raise RuntimeError(
                        f"Network did not recover within {max_network_wait}s"
                    )

            try:
                # Attempt connection with built-in retry logic
                self.client.connect()
                return

            except Exception as e:
                # Check if it's a network error
                if self._is_network_error(e):
                    self.client.logger.warning(
                        f"Network error during connection: {e}"
                    )
                    # Wait for network to recover
                    continue
                else:
                    # Non-network error, re-raise
                    raise

    def _is_network_error(self, error):
        """Check if error is network-related"""
        error_str = str(error).lower()
        network_keywords = [
            'network', 'connection', 'timeout', 'unreachable',
            'refused', 'reset', 'dns'
        ]
        return any(kw in error_str for kw in network_keywords)


# Usage Example
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Start network monitor
    monitor = NetworkMonitor(
        logger=logger,
        required_interfaces=['eth0']  # Monitor specific interface
    )
    monitor.start()

    # Create VMware client (example)
    from hyper2kvm.vmware.clients.client import VMwareClient
    vmware_client = VMwareClient(
        logger=logger,
        host="vcenter.example.com",
        user="administrator@vsphere.local",
        password="password"
    )

    # Wrap with network awareness
    aware_client = NetworkAwareVMwareClient(vmware_client, monitor)

    try:
        # This will wait for network if it's down
        aware_client.connect_with_network_awareness()
        logger.info("Connected successfully!")

        # Your operations here...

    finally:
        monitor.stop()
```

### Integration with Daemon Mode

For daemon mode, add network monitoring to the watcher loop:

```python
# In daemon_watcher.py
def _enhanced_daemon_loop(self):
    monitor = NetworkMonitor(self.logger, required_interfaces=['eth0'])
    monitor.start()

    try:
        while not self.stop_event.is_set():
            # Pause processing if network is down
            if not monitor.network_up.is_set():
                self.logger.warning("Network down, pausing operations...")
                monitor.wait_for_network(timeout=60)
                continue

            # Normal processing...
            self._process_queue()
            time.sleep(self.poll_interval)

    finally:
        monitor.stop()
```

### Configuration

Add to YAML config:

```yaml
cmd: daemon

# Network monitoring
network_monitor:
  enabled: true
  required_interfaces: ["eth0", "ens192"]  # Interfaces to monitor
  max_network_wait_s: 300  # 5 minutes
  pause_on_network_down: true  # Pause operations when network is down

# Connection retry (works with network monitor)
vc_connection_max_retries: 10  # More retries for network issues
vc_connection_base_backoff_s: 5.0
vc_connection_max_backoff_s: 60.0
```

### Installation

```bash
# Install netlink support
pip install pyroute2

# Or add to requirements.txt
echo "pyroute2>=0.7.0" >> requirements.txt
```

### Benefits of Netlink Approach

1. **Immediate notification**: No polling delay
2. **Battery efficient**: Kernel wakes process only on state changes
3. **Reliable**: Direct kernel communication
4. **Low overhead**: Minimal CPU usage
5. **Detailed info**: Link state, IP changes, route changes, neighbor updates

### Alternative: Simple Link Check (No Netlink)

If pyroute2 is not available, fall back to simple link checking:

```python
def check_network_simple():
    """Simple network check without netlink"""
    import socket
    try:
        # Try to connect to known host
        sock = socket.create_connection(("8.8.8.8", 53), timeout=3)
        sock.close()
        return True
    except (socket.timeout, socket.error):
        return False
```

## Recommendations

### For Production Deployments:
1. **Use netlink monitoring** for real-time network state awareness
2. **Set higher retry counts** (`vc_connection_max_retries: 10`)
3. **Enable daemon recovery checkpoints** (`enable_recovery: true`)
4. **Monitor with systemd** (notify socket for health checks)

### For Development/Testing:
1. **Use built-in retry** (already implemented)
2. **Lower retry counts** (`vc_connection_max_retries: 3`)
3. **Enable verbose logging** (`verbose: 2`)

### For Critical Infrastructure:
1. **Combine both approaches**: Netlink + connection retry
2. **Add health checks**: Systemd watchdog
3. **Enable notifications**: Webhook/email on failures
4. **Use connection pooling**: Keep connections alive

---

**See Also:**
- `95-vsphere-connection-retry-example.yaml` - Connection retry configuration
- `daemon-enhanced.yaml` - Enhanced daemon with retry and recovery
