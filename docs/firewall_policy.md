# Firewall Policy

Firewall policy is rendered as vendor-neutral YAML-like text because the final
firewall vendor is unknown.

Current intent:

- NAT outbound for user/voice VLANs.
- Block social media categories for HQ VLAN 20/30/40 and Branch VLAN 50/60.
- Allow Zalo through placeholder FQDN/App-ID object.
- Allow Call App through placeholder FQDN/IP/port object.
- Log deny traffic.

Before production:

- Replace placeholder Zalo FQDN/App-ID with vendor-supported objects.
- Replace Call App placeholder with actual FQDN, IP ranges and ports.
- Confirm policy order on the target firewall.
- Enable logging and retention according to compliance requirements.

An optional FortiGate-style example template is provided in
`templates/firewall/fortigate_example.j2`.
