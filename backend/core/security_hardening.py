"""Enterprise Security Hardening for FormPilot.

Implements high-assurance defense mechanisms for hyper-scale government form-filling:
1. SSRFGuard: Multi-layered Server-Side Request Forgery defense with DNS rebinding protection,
   CIDR block validation (blocking cloud metadata 169.254.169.254, RFC 1918 private subnets,
   loopbacks, IPv6 unroutable addresses), and official portal allowlisting.
2. AuditHashChain: Cryptographic Merkle-style hash chaining for immutable, tamper-evident
   run execution ledgers and non-repudiation.
3. PIISanitizer: Deep PII scrubbing preventing Aadhaar, PAN, phone numbers, and secrets
   from leaking into logs, third-party LLMs, or error traces.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

# Private, reserved, and sensitive IPv4/IPv6 networks that must be blocked
BLOCKED_IP_NETWORKS = [
    # IPv4 loopback
    ipaddress.ip_network("127.0.0.0/8"),
    # RFC 1918 private subnets
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    # AWS / GCP / Azure / OpenStack link-local cloud metadata
    ipaddress.ip_network("169.254.0.0/16"),
    # Broadcast and "this host on this network"
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("255.255.255.255/32"),
    # Carrier-grade NAT (RFC 6598)
    ipaddress.ip_network("100.64.0.0/10"),
    # Documentation / Test-nets (RFC 5737)
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    # Multicast & reserved
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    # IPv6 loopback
    ipaddress.ip_network("::1/128"),
    # IPv6 unique local (RFC 4193)
    ipaddress.ip_network("fc00::/7"),
    # IPv6 link-local
    ipaddress.ip_network("fe80::/10"),
    # IPv4-mapped IPv6
    ipaddress.ip_network("::ffff:0:0/96"),
]

# Cloud metadata IP addresses explicitly forbidden under all circumstances
STRICT_FORBIDDEN_IPS: Set[str] = {
    "169.254.169.254",  # AWS / Azure / GCP metadata
    "fd00:ec2::254",     # AWS IPv6 IMDS
    "100.100.100.200",  # Alibaba Cloud metadata
}

# Regex pattern matching Aadhaar (12 digits, optional spaces)
_AADHAAR_RE = re.compile(r"\b(\d{4})\s?(\d{4})\s?(\d{4})\b")

# Regex pattern matching Indian PAN (5 letters + 4 digits + 1 letter)
_PAN_RE = re.compile(r"\b([A-Z]{5})(\d{4})([A-Z])\b")

# Regex pattern matching Indian phone numbers (10 digits starting with 6, 7, 8, or 9)
_PHONE_RE = re.compile(r"\b(?:\+91|91|0)?([6-9]\d{5})(\d{4})\b")

# Regex pattern matching Email addresses
_EMAIL_RE = re.compile(r"\b([a-zA-Z0-9_.+-])[a-zA-Z0-9_.+-]*@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\b")

# Regex pattern matching Auth headers / Bearer tokens
_AUTH_HEADER_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]+", re.IGNORECASE)

GENESIS_HASH = "0" * 64


class SSRFGuard:
    """Multi-layer SSRF validator preventing unauthorized network traversal."""

    @classmethod
    def is_ip_blocked(cls, ip_str: str) -> bool:
        """Check if an IP string belongs to any blocked subnet or metadata service."""
        if ip_str in STRICT_FORBIDDEN_IPS:
            return True
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
            return True

        # Handle NAT64 translation prefix (RFC 6052 64:ff9b::/96): validate embedded IPv4
        nat64_prefix = ipaddress.ip_network("64:ff9b::/96")
        if ip_obj.version == 6 and ip_obj in nat64_prefix:
            embedded_ipv4 = ipaddress.IPv4Address(ip_obj.packed[-4:])
            return cls.is_ip_blocked(str(embedded_ipv4))

        if ip_obj.is_loopback or ip_obj.is_private or ip_obj.is_link_local or ip_obj.is_multicast or ip_obj.is_unspecified:
            return True

        for network in BLOCKED_IP_NETWORKS:
            if ip_obj in network:
                return True
        return False

    @classmethod
    def resolve_dns_and_check(cls, hostname: str) -> Tuple[bool, List[str], str]:
        """Resolve hostname to IPs and verify none fall in blocked ranges (DNS Rebinding defense)."""
        try:
            # Query IPv4 and IPv6 addresses
            addr_info = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        except socket.gaierror as err:
            return False, [], f"DNS resolution failed for hostname '{hostname}': {err}"
        except Exception as err:
            return False, [], f"Resolution error: {err}"

        resolved_ips: List[str] = []
        for info in addr_info:
            sockaddr = info[4]
            ip_str = sockaddr[0]
            resolved_ips.append(ip_str)
            if cls.is_ip_blocked(ip_str):
                return False, resolved_ips, f"Hostname '{hostname}' resolves to blocked IP '{ip_str}'"

        if not resolved_ips:
            return False, [], f"No IP addresses resolved for hostname '{hostname}'"

        return True, resolved_ips, ""

    @classmethod
    def is_safe_url(cls, url: str, allow_local_simulator: bool = False) -> Tuple[bool, str]:
        """Validate target portal URL against SSRF vulnerabilities.
        
        Args:
            url: The target portal URL to validate.
            allow_local_simulator: If True, permits localhost/127.0.0.1 specifically for
                                  local mock portal development, but NEVER metadata IPs.
        """
        if not url or not isinstance(url, str):
            return False, "Target URL must be a non-empty string"

        try:
            parsed = urlparse(url.strip())
        except Exception as e:
            return False, f"Malformed URL: {e}"

        scheme = (parsed.scheme or "").lower()
        if scheme not in {"http", "https"}:
            return False, f"Disallowed scheme '{scheme}': Only 'http' and 'https' are permitted"

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False, "URL missing valid hostname"

        # Explicitly reject cloud metadata hosts or keywords
        if hostname in STRICT_FORBIDDEN_IPS or "metadata.google.internal" in hostname:
            return False, "Cloud metadata endpoints are strictly forbidden"

        # Check if hostname is an IP address
        try:
            ip_obj = ipaddress.ip_address(hostname)
            is_ip = True
        except ValueError:
            is_ip = False

        if is_ip:
            ip_str = str(ip_obj)
            if allow_local_simulator and ip_obj.is_loopback:
                return True, "Allowed local simulator loopback IP"
            if cls.is_ip_blocked(ip_str):
                return False, f"Target IP '{ip_str}' belongs to a blocked internal or reserved network"
            return True, "IP verified public and safe"

        # Hostname is a domain name. Check localhost exception if allowed
        if hostname in {"localhost", "127.0.0.1"} and allow_local_simulator:
            return True, "Allowed local simulator hostname"

        # Prevent obvious localhost aliases
        if hostname in {"localhost", "ip6-localhost", "ip6-loopback"}:
            return False, "Loopback domain 'localhost' is prohibited"

        # Resolve DNS to check for DNS rebinding attacks pointing to internal services
        safe, _, reason = cls.resolve_dns_and_check(hostname)
        if not safe:
            return False, reason

        return True, "URL verified safe for outbound navigation"


class AuditHashChain:
    """Tamper-evident, cryptographically linked execution ledger."""

    def __init__(self, entries: Optional[List[Dict[str, Any]]] = None) -> None:
        self.entries: List[Dict[str, Any]] = []
        if entries:
            for entry in entries:
                self.entries.append(dict(entry))

    @staticmethod
    def _canonical_payload_hash(data: Any) -> str:
        """Create a deterministic SHA-256 hash of arbitrary payload data."""
        serialized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_entry_hash(index: int, timestamp: str, event_type: str, payload_digest: str, prev_hash: str) -> str:
        """Compute the cryptographic block hash for a chained ledger entry."""
        header = f"{index}|{timestamp}|{event_type}|{payload_digest}|{prev_hash}"
        return hashlib.sha256(header.encode("utf-8")).hexdigest()

    def append(self, event_type: str, data: Any) -> Dict[str, Any]:
        """Append a new event block chained to the previous entry's cryptographic hash."""
        index = len(self.entries)
        prev_hash = self.entries[-1]["entry_hash"] if self.entries else GENESIS_HASH
        timestamp = datetime.now(timezone.utc).isoformat()
        payload_digest = self._canonical_payload_hash(data)
        entry_hash = self.compute_entry_hash(index, timestamp, event_type, payload_digest, prev_hash)

        entry = {
            "index": index,
            "timestamp": timestamp,
            "event_type": event_type,
            "payload_digest": payload_digest,
            "prev_hash": prev_hash,
            "entry_hash": entry_hash,
            "data": data,
        }
        self.entries.append(entry)
        return entry

    def verify(self) -> Tuple[bool, Optional[str]]:
        """Verify the cryptographic chain integrity.
        
        Returns:
            (True, None) if completely valid.
            (False, error_message) if any link or content was tampered with.
        """
        for i, entry in enumerate(self.entries):
            # Verify index sequencing
            if entry.get("index") != i:
                return False, f"Broken sequence at index {i}: expected {i}, found {entry.get('index')}"

            # Verify prev_hash link
            expected_prev = self.entries[i - 1]["entry_hash"] if i > 0 else GENESIS_HASH
            if entry.get("prev_hash") != expected_prev:
                return False, f"Tampered chain link at index {i}: expected prev_hash '{expected_prev}', got '{entry.get('prev_hash')}'"

            # Verify payload digest matches data
            data = entry.get("data")
            computed_digest = self._canonical_payload_hash(data)
            if entry.get("payload_digest") != computed_digest:
                return False, f"Tampered payload data at index {i}: expected digest '{computed_digest}', got '{entry.get('payload_digest')}'"

            # Verify entry hash signature
            computed_hash = self.compute_entry_hash(
                i,
                entry.get("timestamp", ""),
                entry.get("event_type", ""),
                entry.get("payload_digest", ""),
                entry.get("prev_hash", ""),
            )
            if entry.get("entry_hash") != computed_hash:
                return False, f"Forged entry hash at index {i}: expected '{computed_hash}', got '{entry.get('entry_hash')}'"

        return True, None

    def to_list(self) -> List[Dict[str, Any]]:
        return list(self.entries)


class PIISanitizer:
    """Scrub Personally Identifiable Information (PII) before storage or logging."""

    @classmethod
    def mask_text(cls, text: str) -> str:
        if not text or not isinstance(text, str):
            return text

        # Mask Aadhaar numbers: 1234 5678 9012 -> **** **** 9012
        text = _AADHAAR_RE.sub(r"**** **** \3", text)

        # Mask PAN cards: ABCDE1234F -> *****1234*
        text = _PAN_RE.sub(r"*****\2*", text)

        # Mask Phone numbers: 9876543210 -> ******3210
        text = _PHONE_RE.sub(r"******\2", text)

        # Mask Email addresses: john.doe@example.com -> j***@example.com
        text = _EMAIL_RE.sub(r"\1***@\2", text)

        # Redact Authorization Bearer headers
        text = _AUTH_HEADER_RE.sub(r"\1[REDACTED]", text)

        return text

    @classmethod
    def mask_structure(cls, data: Any, depth: int = 0) -> Any:
        """Recursively redact secrets and PII across dicts and lists."""
        if depth > 10:
            return "…"
        if isinstance(data, dict):
            masked_dict = {}
            for k, v in data.items():
                key_str = str(k).lower()
                # If key explicitly indicates secret, redact completely
                if any(sec in key_str for sec in ("password", "passwd", "token", "secret", "cvv", "otp", "totp", "cookie")):
                    masked_dict[k] = "[REDACTED]"
                else:
                    masked_dict[k] = cls.mask_structure(v, depth + 1)
            return masked_dict
        if isinstance(data, list):
            return [cls.mask_structure(item, depth + 1) for item in data]
        if isinstance(data, str):
            return cls.mask_text(data)
        return data
