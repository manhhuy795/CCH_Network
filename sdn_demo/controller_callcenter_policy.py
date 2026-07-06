#!/usr/bin/env python3
"""OpenFlow 1.3 SDN policy controller for the Call Center BPO Mininet demo.

The app works with either OS-Ken or Ryu imports. It reads policy.yml, classifies
IPv4 flows by source/destination IP, installs allow/drop flows, and logs every
policy decision so students can explain the demo clearly.
"""

from pathlib import Path

import yaml

try:
    from os_ken.base import app_manager
    from os_ken.controller import ofp_event
    from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
    from os_ken.lib.packet import arp, ethernet, ether_types, ipv4, packet
    from os_ken.ofproto import ofproto_v1_3
except ImportError:  # pragma: no cover - used when running with Ryu instead of OS-Ken
    from ryu.base import app_manager
    from ryu.controller import ofp_event
    from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
    from ryu.lib.packet import arp, ethernet, ether_types, ipv4, packet
    from ryu.ofproto import ofproto_v1_3


POLICY_FILE = Path(__file__).with_name("policy.yml")


class CallCenterPolicyController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy = self._load_policy()
        self.hosts = self.policy["hosts"]
        self.host_by_ip = {data["ip"]: name for name, data in self.hosts.items()}
        self.gateway_ips = {data["gateway"] for data in self.hosts.values()}
        self.gateway_mac = self.policy["gateway"]["mac"]
        self.allow_pairs, self.deny_pairs = self._build_policy_pairs()
        self.logger.info("Loaded SDN policy: %s", self.policy["metadata"]["name"])
        self.logger.info("Allow pairs: %s", sorted(self.allow_pairs))
        self.logger.info("Deny pairs: %s", sorted(self.deny_pairs))

    def _load_policy(self):
        with POLICY_FILE.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)

    @staticmethod
    def _pair(left, right):
        return left, right

    def _add_bidirectional(self, pairs, left, right):
        pairs.add(self._pair(left, right))
        pairs.add(self._pair(right, left))

    def _build_policy_pairs(self):
        allow_pairs = set()
        deny_pairs = set()
        clients = self.policy["client_hosts"]

        if self.policy.get("voice_enabled", False):
            for client in clients:
                self._add_bidirectional(allow_pairs, client, self.policy["voice_service"])

        for service in self.policy.get("allowed_services", []):
            for client in clients:
                self._add_bidirectional(allow_pairs, client, service)

        for service in self.policy.get("blocked_services", []):
            for client in clients:
                self._add_bidirectional(deny_pairs, client, service)

        for left, right in self.policy.get("deny_pairs", []):
            self._add_bidirectional(deny_pairs, left, right)

        return allow_pairs, deny_pairs

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, event):
        datapath = event.msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        # Table-miss sends first packets to the controller for policy logging.
        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(
                ofproto.OFPP_CONTROLLER,
                ofproto.OFPCML_NO_BUFFER,
            )
        ]
        self._add_flow(datapath, priority=0, match=match, actions=actions)
        self.logger.info("Switch connected: dpid=%s, table-miss installed", datapath.id)

    def _add_flow(self, datapath, priority, match, actions=None, idle_timeout=0):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        instructions = []
        if actions is not None:
            instructions.append(parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions))
        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=instructions,
            idle_timeout=idle_timeout,
        )
        datapath.send_msg(mod)

    def _send_packet(self, datapath, in_port, actions, data):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=ofproto.OFP_NO_BUFFER,
            in_port=in_port,
            actions=actions,
            data=data,
        )
        datapath.send_msg(out)

    def _send_proxy_arp(self, datapath, in_port, request_arp, request_eth):
        parser = datapath.ofproto_parser
        reply = packet.Packet()
        reply.add_protocol(
            ethernet.ethernet(
                ethertype=ether_types.ETH_TYPE_ARP,
                dst=request_eth.src,
                src=self.gateway_mac,
            )
        )
        reply.add_protocol(
            arp.arp(
                opcode=arp.ARP_REPLY,
                src_mac=self.gateway_mac,
                src_ip=request_arp.dst_ip,
                dst_mac=request_arp.src_mac,
                dst_ip=request_arp.src_ip,
            )
        )
        reply.serialize()
        actions = [parser.OFPActionOutput(in_port)]
        self._send_packet(datapath, datapath.ofproto.OFPP_CONTROLLER, actions, reply.data)
        self.logger.info("ALLOW ARP gateway reply: %s asks for %s", request_arp.src_ip, request_arp.dst_ip)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, event):
        msg = event.msg
        datapath = msg.datapath
        parser = datapath.ofproto_parser
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None or eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        arp_pkt = pkt.get_protocol(arp.arp)
        if arp_pkt:
            if arp_pkt.opcode == arp.ARP_REQUEST and arp_pkt.dst_ip in self.gateway_ips:
                self._send_proxy_arp(datapath, in_port, arp_pkt, eth)
            else:
                self.logger.info("DENY ARP non-gateway: %s -> %s", arp_pkt.src_ip, arp_pkt.dst_ip)
            return

        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        if ip_pkt is None:
            self.logger.info("DENY non-IPv4 eth_type=0x%04x", eth.ethertype)
            return

        src_host = self.host_by_ip.get(ip_pkt.src)
        dst_host = self.host_by_ip.get(ip_pkt.dst)
        match = parser.OFPMatch(
            eth_type=ether_types.ETH_TYPE_IP,
            ipv4_src=ip_pkt.src,
            ipv4_dst=ip_pkt.dst,
        )

        if src_host is None or dst_host is None:
            self._add_flow(datapath, priority=100, match=match, actions=None, idle_timeout=30)
            self.logger.info("DENY unknown endpoint: %s -> %s", ip_pkt.src, ip_pkt.dst)
            return

        pair = self._pair(src_host, dst_host)
        if pair in self.deny_pairs:
            self._add_flow(datapath, priority=200, match=match, actions=None, idle_timeout=60)
            self.logger.info("DENY policy: %s(%s) -> %s(%s)", src_host, ip_pkt.src, dst_host, ip_pkt.dst)
            return

        if pair in self.allow_pairs:
            dst_data = self.hosts[dst_host]
            actions = [
                parser.OFPActionSetField(eth_src=self.gateway_mac),
                parser.OFPActionSetField(eth_dst=dst_data["mac"]),
                parser.OFPActionOutput(int(dst_data["switch_port"])),
            ]
            self._add_flow(datapath, priority=300, match=match, actions=actions, idle_timeout=120)
            self._send_packet(datapath, in_port, actions, msg.data)
            self.logger.info("ALLOW policy: %s(%s) -> %s(%s)", src_host, ip_pkt.src, dst_host, ip_pkt.dst)
            return

        self._add_flow(datapath, priority=100, match=match, actions=None, idle_timeout=60)
        self.logger.info("DENY default: %s(%s) -> %s(%s)", src_host, ip_pkt.src, dst_host, ip_pkt.dst)
