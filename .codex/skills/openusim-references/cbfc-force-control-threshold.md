# CBFC Force-Control Threshold

<reference-hint>
<use-when>Use this reference when the user asks how to tune `CbfcForceCtrlThresholdCell`, why CBFC should force a control frame, or whether the threshold should scale with credit size or with propagation budget.</use-when>
<focus>How to interpret the forced control-frame threshold in CBFC, what failure it protects against, and how to tune it from bandwidth-delay and in-flight serialization budget rather than from arbitrary initial-credit ratios.</focus>
<keywords>CBFC, CbfcForceCtrlThresholdCell, credit return, control frame, Crd_Ack Block, threshold, tuning</keywords>
</reference-hint>

## Core Judgment

`CbfcForceCtrlThresholdCell` is not a generic "credit low-watermark".

It is a `pending credit return` threshold:

- local RX has already released credits
- those credits have not yet been returned to the peer TX
- if pending return grows too large, the peer can run out of transmit credits before the forced `Crd_Ack Block` arrives

So the threshold should be chosen from a `credit-return latency budget`, not from an arbitrary fraction of initial credits.

## What The Threshold Protects

The relevant question is:

`how many cells can the upstream sender still consume before my forced control frame arrives and restores credits?`

If the threshold is too large:

- the peer may stall waiting for returned credits
- piggyback-only return becomes too slow under asymmetric traffic

If the threshold is too small:

- control frames are forced too often
- piggyback opportunities are underused
- the model overstates control overhead

## First-Principles Tuning Model

Estimate the cells that the peer can still burn during this window:

`current packet remaining serialization`
`+ forced control-frame serialization`
`+ link propagation delay`

Then convert that byte budget into cells.

In this repo's common default setup:

- link rate: `400Gbps`
- flit size: `20B`
- cell size: `8 flits = 160B`
- control frame size: `2 flits = 40B`
- typical link delay: `20ns`
- practical large data packet budget: about `4KB`

This gives roughly:

- `4KB` data serialization at `400Gbps` -> about `81.9ns`
- control frame serialization -> about `0.8ns`
- propagation -> `20ns`
- total -> about `102.7ns`

At `400Gbps`, that window carries about `4109B`, which is about `26 cells` at `160B/cell`.

That means a threshold around `32 cells` is already close to the minimum "do not let the peer stall before the forced control frame lands" budget.

## Repo Default Rule

This repo currently uses:

- `CbfcForceCtrlThresholdCell = 64`

Why `64` instead of the tighter `~32`-cell latency budget:

- it still stays far below the default initial credit window (`6553` cells)
- it gives piggyback return some room to work before forcing control traffic
- it is still small enough that the peer should not wait long for credits under the common `400Gbps`, `20ns`, `160B/cell` setup

Treat `64` as a practical default, not as a universal optimum.

## Safe Tuning Rules

Start from these rules:

1. If the peer visibly stalls waiting for credit return, lower `CbfcForceCtrlThresholdCell`.
2. If control frames become too frequent while throughput is already healthy, raise it moderately.
3. Tune against:
   - link rate
   - link delay
   - cell size
   - largest practical in-flight data packet serialization that can delay the forced control frame
4. Do not tune this parameter as a fixed percentage of `CbfcInitCreditCell` unless that percentage has been justified by the actual latency budget.

## Safe Wording

- `CbfcForceCtrlThresholdCell` should be tuned from the credit-return latency budget.
- A reasonable default keeps the upstream sender from exhausting credits before the forced control frame arrives.
- In the common repo default setup, `64` cells is a practical default with moderate safety margin.

## Unsafe Wording

- threshold should always be `1/16` of initial credit
- bigger initial credit always means bigger threshold is better
- this threshold means the local port itself is out of credits

## Practical Use

When comparing CBFC settings, change this parameter independently from:

- `CbfcInitCreditCell`
- `CbfcRetCellGrainDataPacket`
- `CbfcRetCellGrainControlPacket`

Interpret the result like this:

- if lower threshold improves peer continuity but increases control-frame count, the old threshold was too lax
- if higher threshold reduces control traffic without hurting peer continuity, the old threshold was too aggressive
