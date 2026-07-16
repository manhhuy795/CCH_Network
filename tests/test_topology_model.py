import re
from pathlib import Path

import yaml

from scripts.network_model import build_host_inventory, controlled_switches, load_network_model, validate_network_model
from sdn_mpls_demo.policy_engine import PolicyEngine


REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO_ROOT / "sdn_mpls_demo" / "policy.yml"
TOPOLOGY_PATH = REPO_ROOT / "sdn_mpls_demo" / "topology_hybrid_sdn.py"
CONTROLLER_PATH = REPO_ROOT / "sdn_mpls_demo" / "controller_policy.py"


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
    assert model["services"]["h90"]["label"] == "PBX/SBC Voice Service"
    assert len(hosts) == len(set(hosts))
    assert len(ips) == len(set(ips))
    assert "voice_access" in controlled_switches(model)
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
    assert len(hosts) == 115
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
    assert any("115 endpoints" in error for error in errors)
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
    assert 'net.addHost("branch_l3_gateway", cls=LinuxRouter, ip=None)' in source
    assert 'switches["core_hq"], hq_l3,' in source
    assert "hq_l3, ce_hq," in source
    assert "ce_hq, mpls_cloud," in source
    assert "ce_branch, mpls_cloud," in source
    assert 'switches["dist_branch"], branch_l3,' in source
    assert "branch_l3, ce_branch," in source
    assert 'net.addLink(switches["dist_branch"], switches["core_hq"]' not in source
    assert 'intfName2=f"{group[\'prefix\']}-u{index:02d}"' in source
    assert 'intfName1="br-eth99"' in source
    assert 'intfName2="dist-eth01"' in source

    explicit_interfaces = re.findall(r'intfName[12]="([^"]+)"', source)
    assert explicit_interfaces
    assert all(len(name) <= 15 for name in explicit_interfaces)
    assert all("-eth" in name for name in explicit_interfaces)


def test_l3_gateways_own_user_gateways_and_ce_only_routes_wan():
    source = TOPOLOGY_PATH.read_text(encoding="utf-8")

    assert 'configure_router_interface(\n        hq_l3,\n        "hq_l3-eth0",' in source
    assert '"172.16.20.1/24"' in source
    assert '"172.16.30.1/24"' in source
    assert '"172.16.40.1/24"' in source
    assert '"172.16.70.1/24"' in source
    assert '"172.16.90.1/24"' in source
    assert 'configure_router_interface(\n        branch_l3,\n        "branch_l3-eth0",' in source
    assert '["172.16.50.1/24", "172.16.60.1/24"]' in source
    assert 'configure_router_interface(ce_hq, "ce_hq-eth0", ["10.255.20.2/30"])' in source
    assert 'configure_router_interface(ce_branch, "ce_branch-eth0", ["10.255.21.2/30"])' in source
    assert 'add_route(hq_l3, "0.0.0.0/0", "10.255.22.2")' in source
    assert 'add_route(branch_l3, "0.0.0.0/0", "10.255.23.2")' in source
    assert 'configure_router_interface(ce_hq,\n        "ce_hq-eth0"' not in source
    assert 'configure_router_interface(ce_branch,\n        "ce_branch-eth0"' not in source


def test_only_expected_ovs_are_controller_managed():
    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    topology = TOPOLOGY_PATH.read_text(encoding="utf-8")

    assert policy["runtime"]["controller"] == "127.0.0.1:6653"
    for switch in (
        "access_hq_a", "access_hq_b", "access_hq_c", "voice_access",
        "core_hq", "access_branch", "dist_branch", "access_hq_it",
    ):
        assert f'"{switch}"' in topology
    assert '"mpls_cloud",' in topology
    assert 'dpid="00000000000000f1"' in topology
    assert '"internet",' in topology
    assert 'dpid="00000000000000f2"' in topology


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


def test_internet_edge_boundary_is_not_claimed_as_stateful_firewall():
    model = load_network_model(REPO_ROOT / "vars" / "network_model.yml")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    sdn_readme = (REPO_ROOT / "sdn_mpls_demo" / "README.md").read_text(encoding="utf-8")
    dashboard_readme = (REPO_ROOT / "dashboard" / "README.md").read_text(encoding="utf-8")
    frontend_policy = (REPO_ROOT / "dashboard" / "frontend" / "src" / "components" / "PolicyPanel.tsx").read_text(encoding="utf-8")

    assert model["infrastructure"]["fw_hq"]["label"] == "HQ Internet Edge Boundary"
    assert model["infrastructure"]["fw_branch"]["label"] == "Branch Internet Edge Boundary"
    assert "khong phai stateful firewall" in model["infrastructure"]["fw_hq"]["subtitle"]
    assert "Simulation Honesty" in readme
    assert "Internet Edge Boundary" in sdn_readme
    assert "khong phai stateful firewall" in dashboard_readme
    assert "Internet Edge Boundary" in frontend_policy


def test_controller_is_real_osken_openflow_13_app():
    controller = CONTROLLER_PATH.read_text(encoding="utf-8")

    assert "app_manager.OSKenApp" in controller
    assert "ofproto_v1_3.OFP_VERSION" in controller
    assert "EventOFPPacketIn" in controller
    assert "OFPFlowMod" in controller
    assert "installed_flows.json" in controller
    assert "install_isolation_flows" in controller
    assert "install_service_policy_flows" in controller
    assert "install_it_support_flows" in controller
    assert "IT Support chi duoc khoi tao ICMP echo-request" in controller
    assert "Block Social Media cho user thuong" in controller
    assert "Chan ping chu dong tu Internet/service vao user noi bo" in controller
    assert "eth_type=ether_types.ETH_TYPE_ARP" in controller
    assert "không bypass IP policy" in controller
    assert "priority=400" in (
        REPO_ROOT / "sdn_mpls_demo" / "topology_hybrid_sdn.py"
    ).read_text(encoding="utf-8")


def test_controller_enforces_drop_policies_only_at_core_and_distribution():
    model = load_network_model(REPO_ROOT / "vars" / "network_model.yml")
    controller = CONTROLLER_PATH.read_text(encoding="utf-8")

    assert model["switches"]["core_hq"]["role"] == "hq_core"
    assert model["switches"]["dist_branch"]["role"] == "branch_distribution"
    assert model["switches"]["access_hq_a"]["role"] == "access"
    assert model["switches"]["access_branch"]["role"] == "access"
    assert 'switch_name == "core_hq" and self.policy.policies["isolate_hq_projects"]' in controller
    assert 'switch_name == "dist_branch" and self.policy.policies["isolate_branch_vlan_50_60"]' in controller
    assert 'Khong cai isolation DROP tren %s; access OVS chi transit/local switching.' in controller
    assert 'switch_name == ENFORCEMENT_SWITCH_BY_GROUP[group_name]' in controller
    assert "hq_social_block" in controller
    assert "branch_social_block" in controller
    assert '"policy": "reactive_policy_drop"' in controller
    assert '"policy": "transit_to_enforcement"' in controller
    assert "POLICY INSTALLED switch=%s role=%s policy=%s priority=%s" in controller


def test_phase27_controller_flow_placement_contract():
    controller = CONTROLLER_PATH.read_text(encoding="utf-8")

    core_section = controller.split('switch_name == "core_hq"', 1)[1].split('if switch_name == "dist_branch"', 1)[0]
    branch_section = controller.split('switch_name == "dist_branch"', 1)[1].split('self.logger.info("Khong cai isolation DROP', 1)[0]

    assert "hq_project_isolation" in controller
    assert "branch_isolation" in controller
    assert "hq_social_block" in controller
    assert "branch_social_block" in controller
    assert "400," in controller
    assert "390," in controller
    assert "POLICY_COOKIES = {" in controller
    assert "POLICY_COOKIES.get(policy_id" in controller
    assert "access_hq_a" not in core_section
    assert "access_hq_b" not in core_section
    assert "access_hq_c" not in core_section
    assert "access_branch" not in branch_section


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

    for cookie in ("0x1001", "0x1002", "0x1003", "0x1004", "0x1100", "0x1200", "0x1301", "0x1302", "0x1303", "0x1304"):
        assert cookie in controller
    assert "cookie=cookie" in controller
    assert 'cookie=f"0x{cookie:x}"' in controller
    assert '"policy": "allowed_services"' in controller
    assert '"policy": "voice"' in controller
    assert '"policy": "it_support"' in controller
    assert "hq_social_block" in controller
    assert "branch_social_block" in controller
    assert "it_support_return" in controller
    assert "it_inbound_block" in controller
    assert "it_social_block" in controller


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
    assert "hqa-core" in runner
    assert "hqa-eth99" in runner
    assert "hq_l3-eth0" in runner
    assert "branch_l3-eth0" in runner
    assert "seq -w 1 10" in runner
    assert 'interface="h70-u${index}"' in runner
    assert "printf 'h70-u%02d'" not in runner
    assert "NETWORK_MODEL = load_network_model()" in topology
    assert "DPIDS = dpid_map(NETWORK_MODEL)" in topology


def test_phase27_live_link_and_policy_reload_hooks_exist():
    topology = TOPOLOGY_PATH.read_text(encoding="utf-8")
    controller = CONTROLLER_PATH.read_text(encoding="utf-8")
    api = (REPO_ROOT / "dashboard" / "backend" / "app" / "api.py").read_text(encoding="utf-8")
    mininet_control = (REPO_ROOT / "dashboard" / "backend" / "app" / "mininet_control.py").read_text(encoding="utf-8")
    policy_module = (REPO_ROOT / "dashboard" / "backend" / "app" / "policy.py").read_text(encoding="utf-8")

    assert "self.net.configLinkStatus(left, right, state)" in topology
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
