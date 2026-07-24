from pathlib import Path


def test_topology_ui_has_new_layers_and_backend_path_animation_hooks():
    source = Path("dashboard/frontend/src/components/TopologyCanvas.tsx").read_text(encoding="utf-8")
    for node in ("access_floor1", "access_floor2", "dist_hq_1", "dist_hq_2", "core_hq", "access_branch", "dist_branch", "infra_access", "mpls_primary", "mpls_backup"):
        assert node in source
    assert "props.decision?.path" in source
    assert "blocked_at" in source
    assert "control-path" in source
    assert "Data path" in source
