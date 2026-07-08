#!/usr/bin/env python3
"""Standalone OpenFlow 1.3 controller for the Call Center SDN demo.

This controller intentionally avoids Ryu/OS-Ken dependencies so the demo can run
reliably on Ubuntu 22.04 with only Mininet, Open vSwitch and PyYAML installed.
It implements the small subset of OpenFlow 1.3 needed for this lab:

- table-miss to controller
- IPv4 allow/drop flow mods
- packet-out for first allowed packet
- proxy ARP replies for fake gateway IPs
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import struct
import threading
from pathlib import Path

import yaml


POLICY_FILE = Path(__file__).with_name("policy.yml")
LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

OF_VERSION = 0x04
OFPT_HELLO = 0
OFPT_ECHO_REQUEST = 2
OFPT_ECHO_REPLY = 3
OFPT_FEATURES_REQUEST = 5
OFPT_FEATURES_REPLY = 6
OFPT_SET_CONFIG = 9
OFPT_PACKET_IN = 10
OFPT_PACKET_OUT = 13
OFPT_FLOW_MOD = 14

OFPP_CONTROLLER = 0xFFFFFFFD
OFPP_ANY = 0xFFFFFFFF
OFPG_ANY = 0xFFFFFFFF
OFP_NO_BUFFER = 0xFFFFFFFF
OFPCML_NO_BUFFER = 0xFFFF

OFPFC_ADD = 0
OFPIT_APPLY_ACTIONS = 4
OFPAT_OUTPUT = 0
OFPAT_SET_FIELD = 25

OXM_OF_CLASS = 0x8000
OXM_IN_PORT = 0
OXM_ETH_DST = 3
OXM_ETH_SRC = 4
OXM_ETH_TYPE = 5
OXM_IPV4_SRC = 11
OXM_IPV4_DST = 12

ETH_TYPE_ARP = 0x0806
ETH_TYPE_IP = 0x0800
ARP_REQUEST = 1
ARP_REPLY = 2


def pad8(data: bytes) -> bytes:
    return data + (b"\x00" * ((8 - len(data) % 8) % 8))


def mac_to_bytes(mac: str) -> bytes:
    return bytes(int(part, 16) for part in mac.split(":"))


def ip_to_bytes(ip: str) -> bytes:
    return ipaddress.ip_address(ip).packed


def oxm(field: int, value: bytes) -> bytes:
    header = (OXM_OF_CLASS << 16) | (field << 9) | len(value)
    return struct.pack("!I", header) + value


def ofp_header(msg_type: int, body: bytes, xid: int) -> bytes:
    return struct.pack("!BBHI", OF_VERSION, msg_type, 8 + len(body), xid) + body


def ofp_match(fields: list[bytes]) -> bytes:
    raw_fields = b"".join(fields)
    length = 4 + len(raw_fields)
    return pad8(struct.pack("!HH", 1, length) + raw_fields)


def action_output(port: int, max_len: int = 0) -> bytes:
    return struct.pack("!HHIH6x", OFPAT_OUTPUT, 16, port, max_len)


def action_set_field(field: int, value: bytes) -> bytes:
    payload = oxm(field, value)
    raw_length = 4 + len(payload)
    padded_length = raw_length + ((8 - raw_length % 8) % 8)
    return struct.pack("!HH", OFPAT_SET_FIELD, padded_length) + payload + (b"\x00" * (padded_length - raw_length))


def instruction_apply_actions(actions: bytes) -> bytes:
    length = 8 + len(actions)
    return struct.pack("!HH4x", OFPIT_APPLY_ACTIONS, length) + actions


def parse_ethernet(frame: bytes) -> dict[str, object] | None:
    if len(frame) < 14:
        return None
    return {
        "dst_mac": frame[0:6],
        "src_mac": frame[6:12],
        "eth_type": struct.unpack("!H", frame[12:14])[0],
        "payload": frame[14:],
    }


def parse_ipv4(frame: bytes) -> tuple[str, str] | None:
    eth = parse_ethernet(frame)
    if not eth or eth["eth_type"] != ETH_TYPE_IP:
        return None
    payload = eth["payload"]
    if len(payload) < 20:
        return None
    return str(ipaddress.ip_address(payload[12:16])), str(ipaddress.ip_address(payload[16:20]))


def parse_arp(frame: bytes) -> dict[str, object] | None:
    eth = parse_ethernet(frame)
    if not eth or eth["eth_type"] != ETH_TYPE_ARP:
        return None
    payload = eth["payload"]
    if len(payload) < 28:
        return None
    return {
        "src_mac": payload[8:14],
        "src_ip": str(ipaddress.ip_address(payload[14:18])),
        "dst_ip": str(ipaddress.ip_address(payload[24:28])),
        "op": struct.unpack("!H", payload[6:8])[0],
    }


class Policy:
    def __init__(self, path: Path):
        self.data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.hosts = self.data["hosts"]
        self.host_by_ip = {host["ip"]: name for name, host in self.hosts.items()}
        self.gateway_ips = {host["gateway"] for host in self.hosts.values()}
        self.gateway_mac = self.data["gateway"]["mac"]
        self.allow_pairs, self.deny_pairs = self._build_pairs()

    @staticmethod
    def _add_bidirectional(pairs: set[tuple[str, str]], left: str, right: str) -> None:
        pairs.add((left, right))
        pairs.add((right, left))

    def _build_pairs(self) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
        allow_pairs: set[tuple[str, str]] = set()
        deny_pairs: set[tuple[str, str]] = set()
        clients = self.data["client_hosts"]

        if self.data.get("voice_enabled", False):
            for client in clients:
                self._add_bidirectional(allow_pairs, client, self.data["voice_service"])

        for service in self.data.get("allowed_services", []):
            for client in clients:
                self._add_bidirectional(allow_pairs, client, service)

        for service in self.data.get("blocked_services", []):
            for client in clients:
                self._add_bidirectional(deny_pairs, client, service)

        for left, right in self.data.get("deny_pairs", []):
            self._add_bidirectional(deny_pairs, left, right)

        return allow_pairs, deny_pairs


class OpenFlowConnection:
    def __init__(self, conn: socket.socket, addr: tuple[str, int], policy: Policy):
        self.conn = conn
        self.addr = addr
        self.policy = policy
        self.xid = 1

    def next_xid(self) -> int:
        self.xid += 1
        return self.xid

    def send(self, msg_type: int, body: bytes = b"", xid: int | None = None) -> None:
        self.conn.sendall(ofp_header(msg_type, body, xid or self.next_xid()))

    def recv_exact(self, length: int) -> bytes:
        chunks = []
        remaining = length
        while remaining:
            chunk = self.conn.recv(remaining)
            if not chunk:
                raise ConnectionError("switch disconnected")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def run(self) -> None:
        logging.info("Switch connected from %s:%s", *self.addr)
        self.send(OFPT_HELLO, xid=1)
        self.send(OFPT_FEATURES_REQUEST)

        while True:
            header = self.recv_exact(8)
            version, msg_type, length, xid = struct.unpack("!BBHI", header)
            body = self.recv_exact(length - 8) if length > 8 else b""
            if version != OF_VERSION:
                logging.warning("Ignoring unsupported OpenFlow version %s", version)
                continue
            if msg_type == OFPT_FEATURES_REPLY:
                self.send_set_config()
                self.install_table_miss()
                logging.info("Switch features received, table-miss installed")
            elif msg_type == OFPT_ECHO_REQUEST:
                self.send(OFPT_ECHO_REPLY, body, xid=xid)
            elif msg_type == OFPT_PACKET_IN:
                self.handle_packet_in(body)

    def send_set_config(self) -> None:
        self.send(OFPT_SET_CONFIG, struct.pack("!HH", 0, OFPCML_NO_BUFFER))

    def install_table_miss(self) -> None:
        actions = action_output(OFPP_CONTROLLER, OFPCML_NO_BUFFER)
        self.add_flow(priority=0, match=ofp_match([]), actions=actions)

    def add_flow(self, priority: int, match: bytes, actions: bytes | None, idle_timeout: int = 0) -> None:
        instructions = b""
        if actions:
            instructions = instruction_apply_actions(actions)
        body = struct.pack(
            "!QQBBHHHIIIH2x",
            0,
            0,
            0,
            OFPFC_ADD,
            idle_timeout,
            0,
            priority,
            OFP_NO_BUFFER,
            OFPP_ANY,
            OFPG_ANY,
            0,
        ) + match + instructions
        self.send(OFPT_FLOW_MOD, body)

    def packet_out(self, in_port: int, actions: bytes, data: bytes) -> None:
        body = struct.pack("!IIH6x", OFP_NO_BUFFER, in_port, len(actions)) + actions + data
        self.send(OFPT_PACKET_OUT, body)

    def handle_packet_in(self, body: bytes) -> None:
        if len(body) < 24:
            return
        in_port = self.extract_in_port(body)
        match_len = struct.unpack("!H", body[18:20])[0]
        data_offset = 16 + ((match_len + 7) // 8 * 8) + 2
        frame = body[data_offset:]

        arp_pkt = parse_arp(frame)
        if arp_pkt:
            self.handle_arp(in_port, arp_pkt)
            return

        ip_pair = parse_ipv4(frame)
        if ip_pair:
            self.handle_ipv4(in_port, frame, ip_pair[0], ip_pair[1])

    def extract_in_port(self, body: bytes) -> int:
        match_len = struct.unpack("!H", body[18:20])[0]
        fields = body[20:16 + match_len]
        index = 0
        while index + 4 <= len(fields):
            header = struct.unpack("!I", fields[index:index + 4])[0]
            field = (header >> 9) & 0x7F
            length = header & 0xFF
            value = fields[index + 4:index + 4 + length]
            if field == OXM_IN_PORT and length == 4:
                return struct.unpack("!I", value)[0]
            index += 4 + length
        return OFPP_CONTROLLER

    def handle_arp(self, in_port: int, pkt: dict[str, object]) -> None:
        if pkt["op"] == ARP_REQUEST and pkt["dst_ip"] in self.policy.gateway_ips:
            reply = self.build_arp_reply(pkt["src_mac"], pkt["src_ip"], pkt["dst_ip"])
            self.packet_out(OFPP_CONTROLLER, action_output(in_port), reply)
            logging.info("ALLOW ARP gateway reply: %s asks for %s", pkt["src_ip"], pkt["dst_ip"])
        else:
            logging.info("DENY ARP non-gateway: %s -> %s", pkt["src_ip"], pkt["dst_ip"])

    def build_arp_reply(self, dst_mac: bytes, dst_ip: str, gateway_ip: str) -> bytes:
        gateway_mac = mac_to_bytes(self.policy.gateway_mac)
        return (
            dst_mac
            + gateway_mac
            + struct.pack("!H", ETH_TYPE_ARP)
            + struct.pack("!HHBBH", 1, ETH_TYPE_IP, 6, 4, ARP_REPLY)
            + gateway_mac
            + ip_to_bytes(gateway_ip)
            + dst_mac
            + ip_to_bytes(dst_ip)
        )

    def handle_ipv4(self, in_port: int, frame: bytes, src_ip: str, dst_ip: str) -> None:
        src_host = self.policy.host_by_ip.get(src_ip)
        dst_host = self.policy.host_by_ip.get(dst_ip)
        match = ofp_match([
            oxm(OXM_ETH_TYPE, struct.pack("!H", ETH_TYPE_IP)),
            oxm(OXM_IPV4_SRC, ip_to_bytes(src_ip)),
            oxm(OXM_IPV4_DST, ip_to_bytes(dst_ip)),
        ])

        if not src_host or not dst_host:
            self.add_flow(priority=100, match=match, actions=None, idle_timeout=60)
            logging.info("DENY unknown endpoint: %s -> %s", src_ip, dst_ip)
            return

        pair = (src_host, dst_host)
        if pair in self.policy.deny_pairs:
            self.add_flow(priority=200, match=match, actions=None, idle_timeout=120)
            logging.info("DENY policy: %s(%s) -> %s(%s)", src_host, src_ip, dst_host, dst_ip)
            return

        if pair in self.policy.allow_pairs:
            dst = self.policy.hosts[dst_host]
            actions = (
                action_set_field(OXM_ETH_SRC, mac_to_bytes(self.policy.gateway_mac))
                + action_set_field(OXM_ETH_DST, mac_to_bytes(dst["mac"]))
                + action_output(int(dst["switch_port"]))
            )
            self.add_flow(priority=300, match=match, actions=actions, idle_timeout=180)
            self.packet_out(in_port, actions, frame)
            logging.info("ALLOW policy: %s(%s) -> %s(%s)", src_host, src_ip, dst_host, dst_ip)
            return

        self.add_flow(priority=100, match=match, actions=None, idle_timeout=120)
        logging.info("DENY default: %s(%s) -> %s(%s)", src_host, src_ip, dst_host, dst_ip)


def serve(host: str = "127.0.0.1", port: int = 6653) -> None:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    policy = Policy(POLICY_FILE)
    logging.info("Loaded policy %s", policy.data["metadata"]["name"])
    logging.info("Listening on %s:%s", host, port)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, port))
        server.listen()
        while True:
            conn, addr = server.accept()
            thread = threading.Thread(
                target=lambda: OpenFlowConnection(conn, addr, policy).run(),
                daemon=True,
            )
            thread.start()


if __name__ == "__main__":
    serve()
