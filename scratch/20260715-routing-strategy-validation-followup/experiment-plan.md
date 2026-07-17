# Routing Latency Follow-up Plan

## Trigger

The original 8 MiB unequal-delay treatments remained bandwidth-dominated. This follow-up is a
separate pre-registered matrix and does not rewrite the original result.

## Claim

For sparse 16 KiB short flows, a 20 us candidate path exposes packet-spray and all-path tail-latency
costs that aggregate bandwidth hides in long-flow tests.

## Controls and Treatments

- `spray-latency`: per-flow HASH64 control versus per-packet HASH64 treatment on three equal-metric paths.
- `all-latency`: per-packet shortest-path control versus per-packet all-path treatment with two non-shortest detours.

## Fixed Controls

RTP, CBFC, 400 Gbps core links, 64 tasks of 16 KiB spaced by 100 us, on-demand TP creation,
detailed observability, sequential execution, and unchanged hash implementation.

## Prediction and Falsification

Treatments should use the delayed path and increase p95 task duration. The claim is falsified if
the delayed path is used but p95 does not increase.

## Checkpoint Policy

Continue the complete four-case matrix unless a case fails to execute.
