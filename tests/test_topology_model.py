import re
from pathlib import Path

import yaml

from scripts.network_model import (
    build_host_inventory,
    controlled_switches,
    load_network_model,
    runtime_switch_name,
    validate_network_model,
)
from sdn_mpls_demo.policy_engine import POLICY_FLOW_PROFILES, PolicyEngine


REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO_ROOT / "sdn_mpls_demo" / "policy.yml"
TOPOLOGY_PATH = REPO_ROOT / "sdn_mpls_demo" / "topology_hybrid_sdn.py"
CONTROLLER_PATH = REPO_ROOT / "sdn_mpls_demo" / "controller_policy.py"
PHASE42_GATE_PATH = REPO_ROOT / "scripts" / "phase42_resource_gate.sh"
PHASE42_NAMESPACE_INVENTORY_PATH = REPO_ROOT / "scripts" / "phase42_namespace_inventory.py"


# NHOM A: topology tests assert inventory, role, node va runtime contract cu the.
def test_network_model_is_single_source_of_truth():
    model = load_network_model(REPO_ROOT / "vars" / "network_model.yml")
    hosts = build_host_inventory(model)
    users = [host for host in hosts.values() if host["kind"] == "user"]
    ips = [host["ip"] for host in hosts.values()]

    assert len(users) == 110
    assert model["host_groups"]["project_a"]["count"] == 20
    assert model["host_groups"]["project_b"]["count"] == 20
    assert model["host_groups"]["project_c"]["count"] == 20
    assert model["host_groups"]["telesale"]["count"] == 20
    assert model["host_groups"]["backoffice"]["count"] == 20
    assert model["host_groups"]["it_support"]["count"] == 10
    assert model["host_groups"]["backoffice"]["site"] == "hq"
    assert model["host_groups"]["backoffice"]["gateway_node"] == "core_hq"
    assert model["services"]["h90"]["label"] == "PBX/SBC Voice Service"
    assert len(hosts) == len(set(hosts))
    assert len(ips) == len(set(ips))
    assert "voice_access" in controlled_switches(model)
    assert set(controlled_switches(model)) == {
        "access_hq_a", "access_hq_b", "access_hq_c", "voice_access", "core_hq",
        "access_telesale", "dist_telesale", "access_hq_it", "access_backoffice",
        "access_iot", "access_guest", "infra_access",
    }
    assert validate_network_model(model) == []

    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    assert "host_groups" not in policy
    assert "services" not in policy

    lab_inventory = (REPO_ROOT / "inventories" / "lab_inventory.yml").read_text(encoding="utf-8")
    production_inventory = (REPO_ROOT / "inventories" / "production_inventory.example.yml").read_text(encoding="utf-8")
    assert "hq-voice-access" in lab_inventory
    assert "voice_access_switch" in lab_inventory
    assert "hq-voice-access" in production_inventory
    assert "hq-voice-mgmt" not in lab_inventory
    assert "voice_mgmt_switch" not in lab_inventory
    assert "hq-voice-mgmt" not in production_inventory


def test_phase27_static_source_of_truth_contract():
    model = load_network_model(REPO_ROOT / "vars" / "network_model.yml")
    hosts = build_host_inventory(model)
    users = [host for host in hosts.values() if host["kind"] == "user"]
    services = [host for host in hosts.values() if host["kind"] == "service"]
    all_ips = [host["ip"] for host in hosts.values()]
    source_files = [
        REPO_ROOT / "vars" / "network_model.yml",
        REPO_ROOT / "sdn_mpls_demo" / "policy.yml",
        REPO_ROOT / "dashboard" / "backend" / "app" / "live_mininet.py",
    ]

    assert len(users) == 110
    assert len(hosts) == 128
    assert len(services) == 5
    assert model["host_groups"]["it_support"]["count"] == 10
    assert model["services"]["h90"]["switch"] == "voice_access"
    assert "voice_access" in controlled_switches(model)
    assert len(all_ips) == len(set(all_ips))
    assert not any("172.10." in path.read_text(encoding="utf-8") for path in source_files)


def test_network_model_validation_catches_inventory_drift():
    model = load_network_model(REPO_ROOT / "vars" / "network_model.yml")
    model["host_groups"]["it_support"]["count"] = 4

    errors = validate_network_model(model)

    assert any("110 user hosts" in error for error in errors)
    assert any("128 endpoints" in error for error in errors)
    assert any("IT Support" in error for error in errors)


def test_hybrid_topology_has_one_hundred_ten_users_and_five_services():
    engine = PolicyEngine(POLICY_PATH)
    users = [host for host in engine.hosts.values() if host["kind"] == "user"]
    services = [host for host in engine.hosts.values() if host["kind"] == "service"]

    assert len(users) == 110
    assert len(services) == 5
    assert engine.hosts["h20_01"]["ip"] == "172.16.20.11"
    assert engine.hosts["h70_10"]["ip"] == "172.16.70.20"
    assert "h70_11" not in engine.hosts
    assert engine.hosts["h60_20"]["ip"] == "172.16.60.30"


def test_topology_forces_intersite_path_through_ce_and_mpls():
    source = TOPOLOGY_PATH.read_text(encoding="utf-8")

    assert 'net.addHost("hq_l3_gateway", cls=LinuxRouter, ip=None)' in source
    assert 'net.addHost("telesale_l3_gateway", cls=LinuxRouter, ip=None)' in source
    assert 'switches["core_hq"], hq_l3,' in source
    assert "hq_l3, ce_hq," in source
    assert "ce_hq, mpls_cloud," in source
    assert "ce_telesale, mpls_cloud," in source
    assert 'switches["dist_telesale"], telesale_l3,' in source
    assert "telesale_l3, ce_telesale," in source
    assert 'switches["dist_telesale"], switches["core_hq"]' not in source
    assert 'switches["access_backoffice"],' in source
    assert 'switches["access_telesale"],' in source
    assert 'intfName2=f"{group.get(\'interface_prefix\', group[\'prefix\'])}-u{index:02d}"' in source
    assert 'intfName1="tel-eth99"' in source
    assert 'intfName2="tdist-eth01"' in source

    explicit_interfaces = re.findall(r'intfName[12]="([^"]+)"', source)
    assert explicit_interfaces
    assert all(len(name) <= 15 for name in explicit_interfaces)
    assert len(explicit_interfaces) == len(set(explicit_interfaces))


def test_l3_gateways_own_user_gateways_and_ce_only_routes_wan():
    source = TOPOLOGY_PATH.read_text(encoding="utf-8")

    assert 'configure_vlan_router_interface(\n        hq_l3,\n        "hq_l3-eth0",' in source
    assert '"172.16.20.1/24"' in source
    assert '"172.16.30.1/24"' in source
    assert '"172.16.40.1/24"' in source
    assert '"172.16.60.1/24"' in source
    assert '"172.16.70.1/24"' in source
    assert '"172.16.80.1/24"' in source
    assert '"172.16.90.1/24"' in source
    assert 'configure_vlan_router_interface(telesale_l3, "tele_l3-eth0", [(50, "172.16.50.1/24")])' in source
    assert '["172.16.50.1/24", "172.16.60.1/24"]' not in source
    assert 'transit_cidr("core_hq_to_ce_hq", "endpoint_b")' in source
    assert 'transit_cidr("ce_telesale_to_dist_telesale", "endpoint_a")' in source
    assert 'transit_cidr("fw_hq_to_internet_zone", "endpoint_a")' in source
    assert 'transit_cidr("fw_telesale_to_internet_zone", "endpoint_a")' in source
    assert "configure_declared_routes(net)" in source


def test_only_expected_ovs_are_controller_managed():
    model = load_network_model(REPO_ROOT / "vars" / "network_model.yml")
    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    topology = TOPOLOGY_PATH.read_text(encoding="utf-8")

    assert policy["runtime"]["controller"] == "127.0.0.1:6653"
    assert len(controlled_switches(model)) == 12
    assert 'for name, dpid in DPIDS.items()' in topology
    assert model["switches"]["access_backoffice"]["runtime_name"] == "access_bo"
    assert runtime_switch_name(model, "access_backoffice") == "access_bo"
    assert "RUNTIME_NODE_NAMES = runtime_switch_map(NETWORK_MODEL)" in topology
    assert 'net.addHost("mpls_cloud", cls=LinuxRouter, ip=None)' in topology
    assert 'net.addHost("internet_zone", cls=LinuxRouter, ip=None)' in topology
    assert 'cls=LinuxBridgeSwitch' in topology
    assert "OVSBridge" not in topology
    assert 'dpid="00000000000000f1"' not in topology
    assert 'dpid="00000000000000f2"' not in topology
    for legacy in ('"access_branch"', '"dist_branch"', '"ce_branch"', '"fw_branch"'):
        assert legacy not in topology


def test_phase42_service_linux_bridge_has_bookkeeping_dpid_without_openflow_control():
    model = load_network_model(REPO_ROOT / "vars" / "network_model.yml")
    topology = TOPOLOGY_PATH.read_text(encoding="utf-8")
    readme = (REPO_ROOT / "sdn_mpls_demo" / "README.md").read_text(encoding="utf-8")
    controlled_dpids = {switch["dpid"] for switch in model["switches"].values() if switch["controlled"]}
    match = re.search(r'^SERVICE_NET_MININET_DPID = "([0-9a-fA-F]+)"$', topology, re.MULTILINE)

    assert match is not None
    bookkeeping_dpid = match.group(1)
    assert re.fullmatch(r"[0-9a-fA-F]{16}", bookkeeping_dpid)
    assert bookkeeping_dpid not in controlled_dpids
    assert len(controlled_dpids) == 12
    assert '"service_net",\n        cls=LinuxBridgeSwitch,\n        dpid=SERVICE_NET_MININET_DPID,' in topology
    assert 'service_net.start([])' in topology
    assert 'service_net.start([controller])' not in topology
    assert '"controlled_ovs": list(DPIDS)' in topology
    assert '"controlled_ovs_count": len(DPIDS)' in topology
    assert "service_net" not in model["switches"]
    assert "12 Open vSwitch" in readme
    assert "SERVICE_NET_MININET_DPID=00000000000000fe" in readme
    assert "khong phai OVS" in readme
    assert "khong ket noi OS-Ken" in readme

    assert '("internet_zone", "service_net")' in topology
    service_ports = {
        "hzalo": "svc-zalo",
        "hcall": "svc-call",
        "hsocial": "svc-social",
        "hinternet": "svc-inet",
    }
    assert all(f'"{name}": "{port}"' in topology for name, port in service_ports.items())
    assert len(model["services"]) == 5
    assert model["services"]["h90"]["switch"] == "voice_access"
    for service_name in ("hzalo", "hcall", "hsocial", "hinternet"):
        service = model["services"][service_name]
        assert service["interface_cidr"].startswith(service["interface_ip"] + "/")
        assert service["subnet"] == f"{service['ip']}/32"
        assert service["gateway"] == model["service_addressing"]["gateway_ip"]


def test_mpls_is_labeled_as_logic_simulation_not_provider_core():
    model = load_network_model(REPO_ROOT / "vars" / "network_model.yml")
    frontend = (REPO_ROOT / "dashboard" / "frontend" / "src" / "components" / "TopologyCanvas.tsx").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    sdn_readme = (REPO_ROOT / "sdn_mpls_demo" / "README.md").read_text(encoding="utf-8")

    assert model["infrastructure"]["mpls_cloud"]["label"] == "MPLS L3VPN Logic Cloud"
    assert "Mo phong logic WAN transport" in model["infrastructure"]["mpls_cloud"]["subtitle"]
    assert "MPLS L3VPN LOGIC" in frontend
    assert "PE/P core, VRF, RD/RT, MP-BGP, LDP" in readme
    assert "MPLS L3VPN Logic Cloud" in sdn_readme
    control_section = frontend.split("controlledNodes.map", 1)[1].split("props.links.filter", 1)[0]
    for forbidden in ("fw_hq", "fw_branch", "ce_hq", "ce_branch", "mpls_cloud"):
        assert forbidden not in control_section


def test_internet_edge_boundary_is_a_stateful_nftables_firewall_in_phase44():
    model = load_network_model(REPO_ROOT / "vars" / "network_model.yml")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    sdn_readme = (REPO_ROOT / "sdn_mpls_demo" / "README.md").read_text(encoding="utf-8")
    dashboard_readme = (REPO_ROOT / "dashboard" / "README.md").read_text(encoding="utf-8")
    frontend_policy = (REPO_ROOT / "dashboard" / "frontend" / "src" / "components" / "PolicyPanel.tsx").read_text(encoding="utf-8")

    assert model["infrastructure"]["fw_hq"]["label"] == "HQ Internet Edge Boundary"
    assert model["infrastructure"]["fw_telesale"]["label"] == "Telesale Internet Edge Boundary"
    assert "Stateful nftables firewall" in model["infrastructure"]["fw_hq"]["subtitle"]
    assert "Simulation Honesty" in readme
    assert "Internet Edge Boundary" in sdn_readme
    assert "stateful nftables" in dashboard_readme.lower()
    assert "Internet Edge Boundary" in frontend_policy


def test_controller_is_real_osken_openflow_13_app():
    controller = CONTROLLER_PATH.read_text(encoding="utf-8")

    assert "app_manager.OSKenApp" in controller
    assert "ofproto_v1_3.OFP_VERSION" in controller
    assert "EventOFPPacketIn" in controller
    assert "OFPFlowMod" in controller
    assert "installed_flows.json" in controller
    assert "install_isolation_flows" in controller
    install_body = controller.split("def install_policy_flows", 1)[1].split("def install_arp_transit_flow", 1)[0]
    assert "install_service_policy_flows" not in install_body
    assert "install_it_support_flows" in controller
    assert "IT Support chi duoc khoi tao ICMP echo-request" in controller
    assert "Internet service policy belongs to the two nftables firewalls" in controller
    assert "eth_type=ether_types.ETH_TYPE_ARP" in controller
    assert "không bypass IP policy" in controller
    assert "priority=400" in (
        REPO_ROOT / "sdn_mpls_demo" / "topology_hybrid_sdn.py"
    ).read_text(encoding="utf-8")


def test_controller_enforces_drop_policies_only_at_core_and_distribution():
    model = load_network_model(REPO_ROOT / "vars" / "network_model.yml")
    controller = CONTROLLER_PATH.read_text(encoding="utf-8")
    engine = PolicyEngine(POLICY_PATH)
    isolation_specs = engine.isolation_flow_specs()

    assert model["switches"]["core_hq"]["role"] == "hq_core"
    assert model["switches"]["dist_telesale"]["role"] == "branch_distribution"
    assert model["switches"]["access_hq_a"]["role"] == "access"
    assert model["switches"]["access_telesale"]["role"] == "access"
    assert {spec["switch"] for spec in isolation_specs} == {"core_hq", "dist_telesale"}
    assert all(spec["action"] == "DROP" for spec in isolation_specs)
    assert "self.policy.isolation_flow_specs()" in controller
    assert 'Khong cai isolation DROP tren %s; access OVS chi transit/local switching.' in controller
    assert "self.install_isolation_flows(datapath)" in controller
    assert '"policy": "reactive_policy_drop"' in controller
    assert '"policy": "transit_to_enforcement"' in controller
    assert "POLICY INSTALLED switch=%s role=%s policy=%s priority=%s" in controller


def test_phase27_controller_flow_placement_contract():
    controller = CONTROLLER_PATH.read_text(encoding="utf-8")
    engine = PolicyEngine(POLICY_PATH)
    specs = engine.isolation_flow_specs()

    assert any(spec["policy"] == "hq_project_isolation" for spec in specs)
    assert any(spec["policy"] == "telesale_backoffice_isolation" for spec in specs)
    assert all(spec["priority"] == 400 for spec in specs)
    assert all(spec["cookie"] in {0x1001, 0x1002} for spec in specs)
    assert {spec["switch"] for spec in specs} == {"core_hq", "dist_telesale"}
    assert "POLICY_COOKIES = {" in controller
    assert "POLICY_COOKIES.get(policy_id" in controller
    assert 'switch_specs = [spec for spec in all_specs if spec["switch"] == switch_name]' in controller
    assert "command=ofproto.OFPFC_DELETE" in controller


def test_runtime_policy_tests_keep_phase28_expected_matrix():
    topology = TOPOLOGY_PATH.read_text(encoding="utf-8")

    assert "POLICY_TESTS = (" in topology
    assert topology.count('("') >= 40
    assert '("IT least privilege", "h20_01", "h70_01", False' in topology
    assert '("IT least privilege", "h70_01", "hsocial", False' in topology
    assert '("IT support", "h70_01", "h20_01", True' in topology
    assert '("IT support", "h70_01", "h30_01", True' in topology
    assert '("IT support", "h70_01", "h50_01", True' in topology
    assert '("IT support", "h70_01", "hcall", True' in topology
    assert '("IT support", "h70_01", "hsocial", True' not in topology
    policy_tests_body = topology.split("POLICY_TESTS = (", 1)[1].split(")\n\ndef endpoint_ip", 1)[0]
    assert policy_tests_body.count("\n    (") == 40


def test_controller_uses_openflow_cookies_for_policy_lifecycle():
    controller = CONTROLLER_PATH.read_text(encoding="utf-8")

    assert {profile["cookie"] for profile in POLICY_FLOW_PROFILES.values()} >= {
        0x1001, 0x1002, 0x1100, 0x1200, 0x1301, 0x1302, 0x1303,
    }
    assert 'policy_id: int(profile["cookie"])' in controller
    assert "cookie=cookie" in controller
    assert 'cookie=f"0x{cookie:x}"' in controller
    assert '"policy": "voice"' in controller
    assert '"policy": "it_support"' in controller
    assert "it_support_return" in controller
    assert "it_inbound_block" in controller


def test_controller_it_support_flows_are_least_privilege():
    controller = CONTROLLER_PATH.read_text(encoding="utf-8")
    it_section = controller.split("def install_it_support_flows", 1)[1].split("def install_voice_flows", 1)[0]

    assert 'it_policy = self.policy.policies.get("it_support_controlled_access") or {}' in it_section
    assert '"allowed_services"' in it_section
    assert '"managed_user_groups"' in it_section
    assert '"denied_services"' in it_section
    assert 'if "ip" in service and name in allowed_services' in it_section
    assert 'if switch_name != "core_hq"' in it_section
    assert '(destination_network, it_network, destination_name, "it_support")' not in it_section
    assert "(user_network, it_network" not in it_section
    assert "icmpv4_type=ICMP_ECHO_REQUEST" in it_section
    assert "icmpv4_type=ICMP_ECHO_REPLY" in it_section
    assert '"policy": "it_support_return"' in it_section
    assert '"policy": "it_inbound_block"' in it_section
    assert '"policy": "it_social_block"' in it_section
    assert '"hsocial"' not in it_section.split("service_destinations", 1)[1].split("social =", 1)[0]
    assert "priority=455" not in it_section
    assert "460," in it_section
    assert "470," in it_section
    assert "IT Support khong duoc bypass chinh sach Social Media" in it_section


def test_topology_runner_auto_starts_and_waits_for_controller():
    runner = (REPO_ROOT / "sdn_mpls_demo" / "run_topology.sh").read_text(encoding="utf-8")
    topology = TOPOLOGY_PATH.read_text(encoding="utf-8")

    assert "controller_is_listening" in runner
    assert "run_controller.sh" in runner
    assert "CONTROLLER_LOG" in runner
    assert "tail -n 40" in runner
    assert "os_ken.cmd.manager|osken-manager" not in runner
    assert "flock -n 9" in runner
    assert "[t]opology_hybrid_sdn.py" in runner
    assert "cleanup_stale_network" in runner
    assert "hqa-eth99" in runner
    assert "bo-eth99" in runner
    assert "tel-eth99" in runner
    assert "tdist-eth01" in runner
    assert "hq_l3-eth0" in runner
    assert "tele_l3-eth0" in runner
    assert "ce_tel-eth0" in runner
    assert "fw_tel-eth0" in runner
    assert "access_bo" in runner
    assert "phase42_resource_baseline.log" in runner
    assert "export LANG=C.UTF-8" in runner
    assert "export LC_ALL=C.UTF-8" in runner
    assert "export PYTHONUTF8=1" in runner
    assert 'sudo env LANG="$LANG" LC_ALL="$LC_ALL" PYTHONUTF8="$PYTHONUTF8"' in runner
    assert "seq -w 1 10" in runner
    assert 'interface="h70-u${index}"' in runner
    assert "printf 'h70-u%02d'" not in runner
    assert "NETWORK_MODEL = load_network_model()" in topology
    assert "DPIDS = dpid_map(NETWORK_MODEL)" in topology


def test_phase42_ubuntu_resource_gate_is_strict_and_runtime_based():
    gate = PHASE42_GATE_PATH.read_text(encoding="utf-8")
    namespace_inventory = PHASE42_NAMESPACE_INVENTORY_PATH.read_text(encoding="utf-8")

    assert "uname -s" in gate
    assert "sudo -v" in gate
    assert "export LANG=C.UTF-8" in gate
    assert "export LC_ALL=C.UTF-8" in gate
    assert "export PYTHONUTF8=1" in gate
    assert "phase42_topology_runtime.json" in gate
    assert "phase42_resource_baseline.log" in gate
    assert "EXPECTED_SERVICES" in namespace_inventory
    assert "EXPECTED_INFRA_NAMESPACES" in namespace_inventory
    assert "EXPECTED_USERS" in namespace_inventory
    assert "_report_set" in namespace_inventory
    assert "phase42_namespace_inventory.py" in gate
    assert "EXPECTED_OVS=(" in gate
    assert "access_bo" in gate
    assert "dist_telesale" in gate
    assert "service_net" not in gate
    assert "is_connected" in gate
    assert "agent_request HEALTH" in gate
    assert "agent_request LIVE_STATUS" in gate
    assert "ovs-ofctl -O OpenFlow13 dump-flows" in gate
    assert "vmstat 1 11" in gate
    assert "RAM_AVAILABLE_PERCENT" in gate
    assert "PHASE BLOCKED" in gate
    assert "UBUNTU RESOURCE GATE PASSED." in gate
    assert "exit 1" in gate


def test_phase27_live_link_and_policy_reload_hooks_exist():
    topology = TOPOLOGY_PATH.read_text(encoding="utf-8")
    controller = CONTROLLER_PATH.read_text(encoding="utf-8")
    api = (REPO_ROOT / "dashboard" / "backend" / "app" / "api.py").read_text(encoding="utf-8")
    mininet_control = (REPO_ROOT / "dashboard" / "backend" / "app" / "mininet_control.py").read_text(encoding="utf-8")
    policy_module = (REPO_ROOT / "dashboard" / "backend" / "app" / "policy.py").read_text(encoding="utf-8")

    assert "self.net.configLinkStatus(left_node.name, right_node.name, state)" in topology
    assert "left_intf.isUp()" in topology
    assert "right_intf.isUp()" in topology
    assert 'request_agent("LINK_DOWN"' not in mininet_control
    assert '"LINK_UP" if state == "up" else "LINK_DOWN"' in mininet_control
    assert "mininet_control.set_link_state(payload.link_id, \"down\")" in api
    assert "mininet_control.set_link_state(payload.link_id, \"up\")" in api
    assert "reload_policy" in controller
    assert "self._delete_cookie(datapath, cookie)" in controller
    assert "install_policy_flows(datapath)" in controller
    assert "toggle_policy" in policy_module
    assert "rollback" in policy_module


def test_osken_version_keeps_controller_cli():
    requirements = (REPO_ROOT / "sdn_mpls_demo" / "requirements.txt").read_text(encoding="utf-8")
    setup = (REPO_ROOT / "sdn_mpls_demo" / "setup_ubuntu_24_04.sh").read_text(encoding="utf-8")

    assert "os-ken==3.1.1" in requirements
    assert "os_ken.cmd.manager" in setup
    assert "osken-manager" in setup
