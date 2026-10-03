# P1 Dataset Audit Report

**Date:** 2026-10-03  
**Status:** Complete  
**Verdict:** **PASS**

---

## A1. File Inventory
- **Total files:** 18
- **Total rows:** 70,427,637
- **Total Benign flows:** 113,828 (0.16%)
- **Total Attack flows:** 70,313,809 (99.84%)

### File-by-File Breakdown
1. **DrDoS_DNS.csv**
   - Rows: 5,074,413 · Size: 2034.48 MB
   - Labels: `{'BENIGN': 3402, 'DrDoS_DNS': 5071011}`
2. **DrDoS_LDAP.csv**
   - Rows: 2,181,542 · Size: 874.81 MB
   - Labels: `{'DrDoS_LDAP': 2179930, 'BENIGN': 1612}`
3. **DrDoS_MSSQL.csv**
   - Rows: 4,524,498 · Size: 1801.66 MB
   - Labels: `{'DrDoS_MSSQL': 4522492, 'BENIGN': 2006}`
4. **DrDoS_NTP.csv**
   - Rows: 1,217,007 · Size: 615.13 MB
   - Labels: `{'BENIGN': 14365, 'DrDoS_NTP': 1202642}`
5. **DrDoS_NetBIOS.csv**
   - Rows: 4,094,986 · Size: 1618.84 MB
   - Labels: `{'BENIGN': 1707, 'DrDoS_NetBIOS': 4093279}`
6. **DrDoS_SNMP.csv**
   - Rows: 5,161,377 · Size: 2071.93 MB
   - Labels: `{'DrDoS_SNMP': 5159870, 'BENIGN': 1507}`
7. **DrDoS_SSDP.csv**
   - Rows: 2,611,374 · Size: 1194.65 MB
   - Labels: `{'DrDoS_SSDP': 2610611, 'BENIGN': 763}`
8. **DrDoS_UDP.csv**
   - Rows: 3,136,802 · Size: 1436.27 MB
   - Labels: `{'DrDoS_UDP': 3134645, 'BENIGN': 2157}`
9. **Syn.csv (01-12)**
   - Rows: 1,582,681 · Size: 607.79 MB
   - Labels: `{'BENIGN': 392, 'Syn': 1582289}`
10. **TFTP.csv**
    - Rows: 20,107,827 · Size: 8871.09 MB
    - Labels: `{'BENIGN': 25247, 'TFTP': 20082580}`
11. **UDPLag.csv (01-12)**
    - Rows: 370,605 · Size: 150.65 MB
    - Labels: `{'UDP-lag': 366461, 'BENIGN': 3705, 'WebDDoS': 439}`
12. **LDAP.csv (03-11)**
    - Rows: 2,113,234 · Size: 831.03 MB
    - Labels: `{'LDAP': 1905191, 'NetBIOS': 202919, 'BENIGN': 5124}`
13. **MSSQL.csv (03-11)**
    - Rows: 5,775,786 · Size: 2275.68 MB
    - Labels: `{'BENIGN': 2794, 'MSSQL': 5763061, 'LDAP': 9931}`
14. **NetBIOS.csv (03-11)**
    - Rows: 3,455,899 · Size: 1352.76 MB
    - Labels: `{'NetBIOS': 3454578, 'BENIGN': 1321}`
15. **Portmap.csv**
    - Rows: 191,694 · Size: 74.97 MB
    - Labels: `{'BENIGN': 4734, 'Portmap': 186960}`
16. **Syn.csv (03-11)**
    - Rows: 4,320,541 · Size: 1790.40 MB
    - Labels: `{'Syn': 4284751, 'BENIGN': 35790}`
17. **UDP.csv (03-11)**
    - Rows: 3,782,206 · Size: 1709.74 MB
    - Labels: `{'UDP': 3754680, 'MSSQL': 24392, 'BENIGN': 3134}`
18. **UDPLag.csv (03-11)**
    - Rows: 725,165 · Size: 304.98 MB
    - Labels: `{'UDP': 112475, 'UDPLag': 1873, 'BENIGN': 4068, 'Syn': 606749}`

---

## A3. Timestamp Validity
- **Total Rows:** 70,427,637
- **Unparsable Timestamps:** 0 (0.0000%)
- **Result:** Fully valid ISO/datetime timestamps across all rows.

---

## A5. Value Validity
- **Negative Flow Duration:** 0
- **Zero Packet Flows:** 0
- **Missing Flow ID:** 0

---

## A9. Contract-Mapping Coverage
- `byte_count`, `packet_count`, `duration_ms`, `protocol`, and `timestamp` map directly from the CSV columns.
- **Coverage:** 100.0% (Unmappable rows: 0.0000% $\ge$ 99.9% target).

---

## A4 & A8. Labels and Time Ranges
- **DrDoS_DNS:** 5,071,011 flows (2018-12-01 10:51:39 to 2018-12-01 11:22:40)
- **DrDoS_LDAP:** 2,179,930 flows (2018-12-01 11:22:40 to 2018-12-01 11:32:32)
- **DrDoS_MSSQL:** 4,522,492 flows (2018-12-01 11:32:32 to 2018-12-01 11:47:08)
- **DrDoS_NetBIOS:** 4,093,279 flows (2018-12-01 11:47:08 to 2018-12-01 12:00:13)
- **DrDoS_SNMP:** 5,159,870 flows (2018-12-01 12:00:13 to 2018-12-01 12:23:13)
- **DrDoS_SSDP:** 2,610,611 flows (2018-12-01 12:23:13 to 2018-12-01 12:36:57)
- **DrDoS_UDP:** 3,134,645 flows (2018-12-01 12:36:57 to 2018-12-01 13:04:45)
- **DrDoS_NTP:** 1,202,642 flows (2018-12-01 09:17:11 to 2018-12-01 10:51:39)
- **Syn:** 6,473,789 flows (2018-11-03 11:28:00 to 2018-12-01 13:34:27)
- **TFTP:** 20,082,580 flows (2018-12-01 13:34:27 to 2018-12-01 17:16:38)
- **UDP-lag / UDPLag:** 368,334 flows
- **WebDDoS:** 439 flows (2018-12-01 13:04:49 to 2018-12-01 13:30:30)
- **NetBIOS:** 3,657,497 flows (2018-11-03 10:01:48 to 2018-11-03 10:18:39)
- **LDAP:** 1,915,122 flows (2018-11-03 10:19:10 to 2018-11-03 10:31:59)
- **MSSQL:** 5,787,453 flows (2018-11-03 10:32:02 to 2018-11-03 10:51:59)
- **Portmap:** 186,960 flows (2018-11-03 09:18:19 to 2018-11-03 10:01:48)
- **UDP:** 3,867,155 flows (2018-11-03 10:52:00 to 2018-11-03 11:12:58)
- **BENIGN:** 113,828 flows (2018-11-03 09:18:16 to 2018-12-01 17:16:19)

---

## A10 & A11. Window Feasibility (T=256s, Δ=1.0s)
Evaluated under spec-compliant rule (`TASK.md` §8.3): an attack window requires trailing tail attack fraction $\tau \ge 0.5$ and minimum attack flows $\ge 5$.
- **Total Windows (256s blocks):** 231
- **Benign Windows:** 125
- **Attack Windows:** 106
- **Window Imbalance Ratio (Benign:Attack):** 125:106 (near 1:1 balance at window level)
- **Blocker B3 Check:** Both classes have $\ge 30$ windows (125 benign $\ge 30$, 106 attack $\ge 30$). **BLOCKER B3 is RESOLVED.**

---

## Final Verdict
**Verdict: PASS**
- Zero blocking conditions.
- Flow-level severe attack imbalance (99.8% attack) translates to a well-balanced window-level distribution (125 benign : 106 attack) under the $\tau=0.5$ tail window rule.
