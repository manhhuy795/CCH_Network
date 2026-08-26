from os_ken.lib.packet import packet, ethernet, ipv4, udp, dhcp

p = packet.Packet()
p.add_protocol(ethernet.ethernet(dst='ff:ff:ff:ff:ff:ff', src='00:11:22:33:44:55', ethertype=0x0800))
p.add_protocol(ipv4.ipv4(dst='255.255.255.255', src='0.0.0.0', proto=17))
p.add_protocol(udp.udp(dst_port=67, src_port=68))
opts = dhcp.options([dhcp.option(dhcp.DHCP_MESSAGE_TYPE_OPT, b'\x01')])
p.add_protocol(dhcp.dhcp(op=1, chaddr='00:11:22:33:44:55', options=opts))
p.serialize()
print('Serialized length:', len(p.data))
parsed = packet.Packet(p.data)
dh = parsed.get_protocol(dhcp.dhcp)
print('Parsed op:', dh.op, 'chaddr:', dh.chaddr)
