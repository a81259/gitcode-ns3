# Routing Strategy Validation Results

- semantic checkpoint: passed: {"sem-packet-all": [1, 2, 3], "sem-flow-short": [1], "sem-flow-all": [2], "sem-packet-short": [1]}
- successful cases: 56/56
- packet records are exact-record deduplicated; different time/path records are retained.

| case | status | paths | Jain | inversions | mean FCT us | p95 FCT us |
|---|---:|---:|---:|---:|---:|---:|
| sem-flow-short | success | 1 | 1.0 | 0 | 85.857074 | 85.857074 |
| sem-packet-short | success | 1 | 1.0 | 0 | 85.857074 | 85.857074 |
| sem-flow-all | success | 1 | 0.333333 | 0 | 85.795074 | 85.795074 |
| sem-packet-all | success | 3 | 0.997453 | 532 | 30.404425 | 30.404425 |
| hash-many-hash64 | success | 8 | 0.927536 | 0 | 161.85471 | 255.57902 |
| hash-elephant-hash64 | success | 4 | 0.5 | 0 | 1369.62477 | 1369.63226 |
| hash-many-crc32 | success | 4 | 0.5 | 0 | 339.751454 | 342.78658 |
| hash-elephant-crc32 | success | 1 | 0.125 | 0 | 5475.91478 | 5476.41566 |
| hash-many-toeplitz | success | 8 | 1.0 | 0 | 170.490952 | 171.74698 |
| hash-elephant-toeplitz | success | 4 | 0.5 | 0 | 1369.62062 | 1369.62062 |
| spray-equal-flow-hash | success | 1 | 0.333333 | 0 | 171.419954 | 171.419954 |
| spray-equal-packet-hash | success | 3 | 0.999964 | 1060 | 59.920031 | 59.920031 |
| spray-equal-round-robin | success | 3 | 0.999992 | 950 | 57.696847 | 57.696847 |
| spray-delay-flow-hash | success | 1 | 0.333333 | 0 | 171.419954 | 171.419954 |
| spray-delay-packet-hash | success | 3 | 0.999964 | 883 | 63.449618 | 63.449618 |
| spray-delay-round-robin | success | 3 | 1.0 | 650 | 63.059906 | 63.059906 |
| adaptive-hot-hash | success | 3 | 0.999964 | 673 | 227.134448 | 227.134448 |
| adaptive-hot-adaptive | success | 3 | 0.848677 | 617 | 92.473194 | 92.473194 |
| adaptive-sparse-rr | success | 3 | 0.999512 | 0 | 0.231194 | 0.231194 |
| adaptive-sparse-adaptive | success | 1 | 0.333333 | 0 | 0.231194 | 0.231194 |
| stripe-multi-hash | success | 6 | 0.571429 | 0 | 599.38651 | 1027.23518 |
| stripe-multi-stripe | success | 8 | 1.0 | 0 | 342.87102 | 342.87102 |
| stripe-single-hash | success | 4 | 0.444444 | 0 | 473.95396 | 514.15878 |
| stripe-single-stripe | success | 1 | 0.125 | 0 | 1359.07982 | 1369.60078 |
| all-hot-short | success | 1 | 1.0 | 0 | 2739.365074 | 2739.365074 |
| all-hot-all | success | 3 | 0.999964 | 581 | 908.599248 | 908.599248 |
| all-delay-short | success | 1 | 1.0 | 0 | 171.419954 | 171.419954 |
| all-delay-all | success | 3 | 0.999964 | 1017 | 66.345997 | 66.345997 |
| cover-hash64-per-flow-all-paths | success | 0 |  | 0 | 21.682434 | 21.682434 |
| cover-hash64-per-packet-all-paths | success | 0 |  | 0 | 9.246394 | 9.246394 |
| cover-hash64-per-flow-shortest-paths | success | 0 |  | 0 | 21.688634 | 21.688634 |
| cover-hash64-per-packet-shortest-paths | success | 0 |  | 0 | 21.688634 | 21.688634 |
| cover-crc32-per-flow-all-paths | success | 0 |  | 0 | 21.688634 | 21.688634 |
| cover-crc32-per-packet-all-paths | success | 0 |  | 0 | 8.858841 | 8.858841 |
| cover-crc32-per-flow-shortest-paths | success | 0 |  | 0 | 21.688634 | 21.688634 |
| cover-crc32-per-packet-shortest-paths | success | 0 |  | 0 | 21.688634 | 21.688634 |
| cover-toeplitz-per-flow-all-paths | success | 0 |  | 0 | 21.682434 | 21.682434 |
| cover-toeplitz-per-packet-all-paths | success | 0 |  | 0 | 8.412382 | 8.412382 |
| cover-toeplitz-per-flow-shortest-paths | success | 0 |  | 0 | 21.688634 | 21.688634 |
| cover-toeplitz-per-packet-shortest-paths | success | 0 |  | 0 | 21.688634 | 21.688634 |
| cover-round-robin-per-packet-all-paths | success | 0 |  | 0 | 7.586724 | 7.586724 |
| cover-round-robin-per-packet-shortest-paths | success | 0 |  | 0 | 21.688634 | 21.688634 |
| cover-adaptive-per-packet-all-paths | success | 0 |  | 0 | 7.575315 | 7.575315 |
| cover-adaptive-per-packet-shortest-paths | success | 0 |  | 0 | 21.688634 | 21.688634 |
| cover-ingress-port-stripe-per-flow-all-paths | success | 0 |  | 0 | 21.688634 | 21.688634 |
| cover-ingress-port-stripe-per-flow-shortest-paths | success | 0 |  | 0 | 21.688634 | 21.688634 |
| smoke-ctp-flow-hash | success | 0 |  | 0 | 21.462854 | 21.462854 |
| smoke-ctp-packet-hash | success | 0 |  | 0 | 7.854873 | 7.854873 |
| smoke-ctp-round-robin | success | 0 |  | 0 | 7.414139 | 7.414139 |
| smoke-ctp-adaptive | success | 0 |  | 0 | 7.469232 | 7.469232 |
| smoke-ctp-ingress-stripe | success | 0 |  | 0 | 21.462854 | 21.462854 |
| smoke-ldst-flow-hash | success | 0 |  | 0 | 22.305254 | 22.305254 |
| smoke-ldst-packet-hash | success | 0 |  | 0 | 7.908854 | 7.908854 |
| smoke-ldst-round-robin | success | 0 |  | 0 | 7.566854 | 7.566854 |
| smoke-ldst-adaptive | success | 0 |  | 0 | 7.574054 | 7.574054 |
| smoke-ldst-ingress-stripe | success | 0 |  | 0 | 22.305254 | 22.305254 |
