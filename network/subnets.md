
# Task 5: Subnetting and Network Access Control

## 1. Subnet Allocation

Given IPv4 block: `10.20.0.0/16`

The subnets are allocated from largest to smallest based on the required number of hosts.

| Subnet | Required Hosts | Network Address | Prefix | Usable IP Range | Broadcast Address | Usable Hosts |
|---|---:|---|---|---|---|---:|
| App | 1000 | 10.20.0.0 | /22 | 10.20.0.1 - 10.20.3.254 | 10.20.3.255 | 1022 |
| Public | 250 | 10.20.4.0 | /24 | 10.20.4.1 - 10.20.4.254 | 10.20.4.255 | 254 |
| Data | 100 | 10.20.5.0 | /25 | 10.20.5.1 - 10.20.5.126 | 10.20.5.127 | 126 |
| Management | 20 | 10.20.5.128 | /27 | 10.20.5.129 - 10.20.5.158 | 10.20.5.159 | 30 |

## 2. Subnet Calculations

### App Subnet

Required hosts: 1000

\[
2^{10}-2=1022
\]

10 host bits are required.

Prefix:

\[
32-10=22
\]

Network: `10.20.0.0/22`

### Public Subnet

Required hosts: 250

\[
2^8-2=254
\]

8 host bits are required.

Prefix:

\[
32-8=24
\]

Network: `10.20.4.0/24`

### Data Subnet

Required hosts: 100

\[
2^7-2=126
\]

7 host bits are required.

Prefix:

\[
32-7=25
\]

Network: `10.20.5.0/25`

### Management Subnet

Required hosts: 20

\[
2^5-2=30
\]

5 host bits are required.

Prefix:

\[
32-5=27
\]

Network: `10.20.5.128/27`

## 3. Network Access Control List

The Network Access Control List (NACL) is configured for the public subnet `10.20.4.0/24`.

### Inbound Rules

- Deny all traffic from `198.51.100.0/24`.
- Allow TCP port 80 from anywhere.
- Allow TCP port 443 from anywhere.
- Allow TCP port 22 only from the management subnet `10.20.5.128/27`.
- Allow TCP replies from the app subnet `10.20.0.0/22` to ephemeral ports `1024-65535`.
- Deny all other inbound traffic.

### Outbound Rules

- Allow TCP port 8000 to the app subnet `10.20.0.0/22`.
- Allow TCP replies to clients anywhere on ephemeral ports `1024-65535`.
- Deny all other outbound traffic.

## 4. Stateless NACL Explanation

A Network Access Control List is stateless. It does not automatically remember the state of a connection.

Therefore, inbound and outbound traffic must be permitted using separate rules. For example, allowing an inbound HTTP request does not automatically allow the response to leave the subnet.

Rule ordering is important because the NACL evaluates rules in ascending order by rule number. The first matching rule determines whether the packet is allowed or denied.

The deny rule for `198.51.100.0/24` is assigned a lower rule number than the HTTP and HTTPS allow rules so that traffic from this blocked CIDR is denied even when it uses web ports.
