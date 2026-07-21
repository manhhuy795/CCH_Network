import pytest

from sdn_mpls_demo.firewall_nftables import (
    FirewallPolicyError,
    _node_command,
)


class FakeNode:
    name = "fw_hq"

    def __init__(self, output: str):
        self.output = output
        self.command = ""

    def cmd(self, command: str) -> str:
        self.command = command
        return self.output


@pytest.mark.parametrize(
    (
        "output",
        "expected_code",
        "expected_cleaned",
    ),
    [
        (
            "\n__CCH_NFT_EXIT__=0\n",
            0,
            "",
        ),
        (
            "\n__CCH_NFT_EXIT__=0",
            0,
            "",
        ),
        (
            "\r\n__CCH_NFT_EXIT__=0\r\n",
            0,
            "",
        ),
        (
            "\r\n  __CCH_NFT_EXIT__=0\r\n",
            0,
            "",
        ),
        (
            "\r\n__CCH_NFT_EXIT__=0  \r\n",
            0,
            "",
        ),
        (
            "nft output\n"
            "__CCH_NFT_EXIT__=0\n",
            0,
            "nft output",
        ),
        (
            "nft output\r\n"
            "__CCH_NFT_EXIT__=0\r\n",
            0,
            "nft output",
        ),
        (
            "nft error\r\n"
            "__CCH_NFT_EXIT__=1\r\n",
            1,
            "nft error",
        ),
    ],
)
def test_node_command_accepts_terminal_line_endings(
    output: str,
    expected_code: int,
    expected_cleaned: str,
):
    node = FakeNode(output)

    code, cleaned = _node_command(
        node,
        "nft --check --file '/tmp/fw_hq.nft'",
    )

    assert code == expected_code
    assert cleaned == expected_cleaned
    assert "__CCH_NFT_EXIT__=" in node.command


def test_node_command_uses_final_marker():
    node = FakeNode(
        "__CCH_NFT_EXIT__=9\r\n"
        "command output\r\n"
        "__CCH_NFT_EXIT__=0\r\n"
    )

    code, cleaned = _node_command(node, "true")

    assert code == 0
    assert cleaned == "command output"


def test_node_command_rejects_missing_marker():
    node = FakeNode(
        "nft output without an exit marker\r\n"
    )

    with pytest.raises(
        FirewallPolicyError,
        match="Khong doc duoc exit code nftables",
    ):
        _node_command(node, "true")
