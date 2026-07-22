# Ghi ch? b?o m?t

## Token

Operator token ??c t? logs/operator.token v?i quy?n file h?n ch?. Kh?ng commit token, kh?ng ??a token v?o URL, stdout, JSON summary, screenshot ho?c frontend bundle. Gate redaction token tr??c khi l?u output.

Control agent d?ng UNIX socket v? token n?i b?. HEALTH ph?i l? request th?t; socket file ??n ??c kh?ng ch?ng minh agent c?n s?ng.

## Quy?n

Backend c?n quy?n ??c namespace Mininet. Ch?y b?ng user c? sudo policy ph? h?p v? kh?ng d?ng sudo pip. Gate runtime d?ng quy?n root ?? ??c OVS/namespace, kh?ng thay Python h? th?ng.

## Command execution

API kh?ng nh?n raw shell command. Command n?i b? d?ng argv list v? shell=False. C?c script stop ch? d?ng PID do ch?nh script t?o; kh?ng d?ng killall, pkill r?ng ho?c thao t?c cleanup chung kh?ng c? operator ch? ??ng.

## Network policy

OpenFlow enforcement v? nftables boundary l? hai l?p kh?c nhau. Kh?ng coi file installed_flows.json l? flow s?ng. Kh?ng c?p full access ch? v? user c?i softphone; SIP registration, RTP, SBC/NAT v? QoS ph?i ???c ki?m tra ri?ng.

## Gi?i h?n

??y l? simulation/lab. Kh?ng d?ng k?t qu? ping/iperf c?a lab l?m b?ng ch?ng production. Tr??c tri?n khai th?t ph?i c? change approval, backup, rollback, logging, RBAC, secrets management v? ki?m th? failure/recovery.
