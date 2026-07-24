from scripts.network_model import build_host_inventory, load_network_model


def test_hq_floor_placement_matches_enterprise_design():
    hosts = build_host_inventory(load_network_model())
    assert {hosts[f"h20_{i:02d}"]["switch"] for i in range(1, 21)} == {"access_floor1"}
    assert {hosts[f"h30_{i:02d}"]["switch"] for i in range(1, 11)} == {"access_floor1"}
    assert {hosts[f"h30_{i:02d}"]["switch"] for i in range(11, 21)} == {"access_floor2"}
    assert {hosts[f"h30_{i:02d}"]["floor"] for i in range(1, 11)} == {"floor1"}
    assert {hosts[f"h30_{i:02d}"]["floor"] for i in range(11, 21)} == {"floor2"}
    assert {hosts[f"h40_{i:02d}"]["switch"] for i in range(1, 21)} == {"access_floor2"}
    assert {hosts[f"h60_{i:02d}"]["switch"] for i in range(1, 21)} == {"access_floor2"}
    assert {hosts[f"h70_{i:02d}"]["switch"] for i in range(1, 11)} == {"access_floor2"}


def test_guest_and_hq_iot_are_floor_one_only():
    model = load_network_model()
    assert model["host_groups"]["guest"]["floor"] == "floor1"
    assert model["host_groups"]["iot_hq"]["floor"] == "floor1"
    assert model["host_groups"]["guest"]["switch"] == "access_floor1"
    assert model["host_groups"]["iot_hq"]["switch"] == "access_floor1"
