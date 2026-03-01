"""Scan the local network, resolve device hostnames, and report ping status.

Auto-detects the local subnet (assuming /24) and pings each IP concurrently,
resolving hostnames via reverse DNS for reachable hosts.
"""

import argparse
import ipaddress
import logging
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

DEFAULT_WORKERS = 50
DEFAULT_TIMEOUT = 1

log = logging.getLogger(__name__)


# --- Network detection -------------------------------------------------------


def detect_local_network() -> ipaddress.IPv4Network:
    """Auto-detect the local /24 network from the machine's default IP."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    finally:
        s.close()
    log.debug("Detected local IP: %s", local_ip)
    return ipaddress.IPv4Network(f"{local_ip}/24", strict=False)


# --- Scanning ----------------------------------------------------------------


def ping_host(ip: str, timeout: int) -> bool:
    """Ping a single host. Returns True if reachable."""
    result = subprocess.run(
        ["ping", "-c", "1", "-W", str(timeout), ip],
        capture_output=True,
    )
    return result.returncode == 0


def resolve_hostname(ip: str) -> str:
    """Reverse-DNS lookup. Returns hostname or empty string on failure."""
    try:
        hostname, _, _ = socket.gethostbyaddr(ip)
        return hostname
    except socket.herror:
        return ""


def scan_network(
    network: ipaddress.IPv4Network, *, workers: int, timeout: int
) -> list[dict]:
    """Ping all hosts on the network concurrently and resolve hostnames."""
    hosts = [str(ip) for ip in network.hosts()]
    log.info("Scanning %d hosts on %s ...", len(hosts), network)

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(ping_host, ip, timeout): ip for ip in hosts}
        for future in as_completed(futures):
            ip = futures[future]
            alive = future.result()
            hostname = resolve_hostname(ip) if alive else ""
            results.append({"ip": ip, "hostname": hostname, "alive": alive})

    results.sort(key=lambda r: ipaddress.IPv4Address(r["ip"]))
    return results


# --- Output ------------------------------------------------------------------


def print_table(results: list[dict]) -> None:
    """Pretty-print scan results as a terminal table."""
    alive_results = [r for r in results if r["alive"]]
    dead_count = len(results) - len(alive_results)

    if not alive_results:
        print("No reachable hosts found.")
        return

    ip_width = max(len(r["ip"]) for r in alive_results)
    host_width = max((len(r["hostname"]) for r in alive_results), default=0)
    ip_width = max(ip_width, len("IP"))
    host_width = max(host_width, len("HOSTNAME"))

    header = f"{'IP':<{ip_width}}  {'HOSTNAME':<{host_width}}  STATUS"
    sep = f"{'-' * ip_width}  {'-' * host_width}  ------"
    print(header)
    print(sep)
    for r in alive_results:
        print(f"{r['ip']:<{ip_width}}  {r['hostname']:<{host_width}}  up")

    print(f"\n{len(alive_results)} host(s) up, {dead_count} down")


# --- CLI ---------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan local network IPs, resolve hostnames, and report ping status.",
    )
    parser.add_argument(
        "--network",
        default=None,
        help="Network CIDR to scan (default: auto-detect local /24)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Parallel ping threads (default: {DEFAULT_WORKERS})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Ping timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )

    if args.network:
        try:
            network = ipaddress.IPv4Network(args.network, strict=False)
        except ValueError:
            log.error("Invalid network CIDR: %s", args.network)
            sys.exit(1)
    else:
        network = detect_local_network()

    results = scan_network(network, workers=args.workers, timeout=args.timeout)
    print_table(results)
