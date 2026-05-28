# UB Transport Retransmission Refactor Design

## Goal

Refactor RTP retransmission logic out of `ub-transport.cc` into a dedicated
`ub-retrans.h/.cc` module under `src/unified-bus/model/protocol/`.

The refactor should keep existing external behavior and ns-3 attributes stable
while making `UbTransportChannel` focus on common transport flow:

- packet parsing and packet construction
- ACK/CNP queues
- WQE segment scheduling and completion
- receive buffering and transaction completion
- trace callbacks
- congestion control integration points
- port transmit triggering

The new retransmission module owns retransmission policy, RTO management, and
mode-specific retransmission state.

## Specification Context

UB Base Specification 2.0.1 section 6.4.2 defines retransmission as two axes:

- retransmission scope: GoBackN or selective retransmission
- trigger mode: fast retransmission or timeout retransmission

Timeout retransmission is mandatory. Fast retransmission is optional. When both
are enabled, timeout retransmission is the fallback for cases such as tail data
packet loss, tail ACK/SACK loss, or lost negative/selective feedback.

The refactor should preserve these four effective operating modes:

- GBN with fast retransmission
- GBN without fast retransmission
- selective retransmission with fast retransmission
- selective retransmission without fast retransmission

Selective retransmission with fast retransmission may also enable MarkPSN. The
MarkPSN state must move out of `UbTransportChannel`.

## New Files

Add:

- `src/unified-bus/model/protocol/ub-retrans.h`
- `src/unified-bus/model/protocol/ub-retrans.cc`

Update:

- `src/unified-bus/CMakeLists.txt`

The public header list should include `model/protocol/ub-retrans.h` only if
tests or other modules need to include retransmission types directly. Otherwise
it can remain an internal model header included by `ub-transport.h/.cc`.

## High-Level Architecture

`UbTransportChannel` owns one retransmission controller:

```cpp
std::unique_ptr<UbRetransController> m_retrans;
```

The retransmission module contains:

```cpp
class UbRetransController;
class UbRetransStrategy;
class UbGbnRetransStrategy;
class UbSelectiveRetransStrategy;
```

`UbRetransController` is the stable integration point used by
`UbTransportChannel`. It owns common retransmission configuration and RTO state,
selects the active strategy, and delegates mode-specific behavior.

`UbRetransStrategy` is the abstract mode interface. `UbGbnRetransStrategy` and
`UbSelectiveRetransStrategy` implement GBN and selective behavior.

The controller may hold a reference to `UbTransportChannel`, but access should
go through narrow transport methods. The retransmission module should not become
a second transport implementation that freely edits unrelated channel state.

## State Ownership

Move these common retransmission fields from `UbTransportChannel` to
`UbRetransController`:

- retransmission enabled flag
- initial RTO
- current RTO
- max retransmission attempts
- remaining retransmission attempts
- retransmission exponent factor
- retransmission timer event
- retransmission mode
- fast retransmission flag
- selective ACK bitmap configuration
- selective MarkPSN enable flag

Move these selective-only fields to `UbSelectiveRetransStrategy`:

- sent PSN state map
- selective retransmission queue
- per-PSN ACK/missing/retransmit counters
- MarkPSN retransmission phase flag
- MarkPSN awaiting-first-new flag
- MarkPSN validity and value
- last first selective retransmission PSN validity and value

Move this GBN-only field to `UbGbnRetransStrategy`:

- last GBN NAK PSN suppression state

Keep these common transport fields in `UbTransportChannel`:

- send and receive PSN cursors
- highest received PSN
- received-any-PSN flag
- receive bitmap/window
- buffered inbound packet map
- WQE segment vector
- ACK and CNP queues
- congestion control object
- trace sources and trace helpers
- transaction completion helpers

These fields participate in normal transport send/receive behavior, not only
retransmission.

## Controller Interface

The controller should provide high-level methods that match transport events:

```cpp
class UbRetransController
{
public:
    explicit UbRetransController(UbTransportChannel& transport);

    Ptr<Packet> TryGetNextRetransmissionPacket();

    void OnNewDataPacketSent(uint64_t psn,
                             Ptr<Packet> packet,
                             uint32_t payloadBytes,
                             uint32_t logicalBytes,
                             Ptr<UbWqeSegment> segment);

    UbRetransAckResult OnTransportResponse(const UbTransportHeader& tph,
                                           TpOpcode opcode,
                                           const UbSelectiveAckExtTph* saetph,
                                           const UbCongestionExtTph* cetph);

    UbRetransReceiveDecision OnDataPacketReceived(const UbTransportHeader& tph,
                                                  uint32_t payloadBytes,
                                                  uint32_t logicalBytes);

    UbRetransTimeoutResult OnTimeout();

    void StartTimerIfNeeded();
    void RestartTimerAfterAckProgress();
    void CancelTimer();
};
```

The exact signatures may change during implementation, but the direction should
hold: transport reports events, retransmission returns decisions.

## Result Types

Use small result structures instead of long parameter lists.

```cpp
struct UbRetransAckResult
{
    bool ackAdvanced{false};
    uint64_t previousSndUna{0};
    uint64_t newSndUna{0};
    bool triggerTransmit{false};
};

struct UbRetransReceiveDecision
{
    bool dropPacket{false};
    bool shouldAck{false};
    bool shouldNak{false};
    bool selectiveAck{false};
    uint64_t responsePsn{0};
    TpOpcode responseOpcode{TpOpcode::TP_OPCODE_ACK_WITHOUT_CETPH};
    std::optional<UbSelectiveAckExtTph> selectiveAckHeader;
};

struct UbRetransTimeoutResult
{
    bool triggerTransmit{false};
};
```

`UbTransportChannel` applies these decisions by doing the actual packet
construction, queue insertion, trace calls, timer interactions, and port trigger.

## Transport Flow After Refactor

`GetNextPacket()` should keep the control packet priority and delegate only
retransmission packet selection:

```cpp
SendCnpIfAny();
SendAckIfAny();

if (Ptr<Packet> p = m_retrans->TryGetNextRetransmissionPacket()) {
    return p;
}

return TrySendNewDataPacket();
```

After a new data packet is generated and accepted by congestion control:

```cpp
m_retrans->OnNewDataPacketSent(psn, packet, payloadBytes, logicalBytes, segment);
m_retrans->StartTimerIfNeeded();
```

`RecvTpAck()` should parse the response and delegate mode-specific ACK/SACK/NAK
semantics:

```cpp
UbRetransAckResult result =
    m_retrans->OnTransportResponse(tph, opcode, saetphOrNull, cetphOrNull);

ApplyAckProgress(result);
```

`RecvDataPacket()` should parse headers and track common receive state, then ask
the retransmission module what response, if any, is required:

```cpp
UbRetransReceiveDecision decision =
    m_retrans->OnDataPacketReceived(tph, payloadBytes, logicalBytes);

ApplyReceiveDecision(decision);
MaybeQueueTransportResponse(decision);
```

`ReTxTimeout()` can become a thin forwarding method:

```cpp
m_retrans->OnTimeout();
```

The controller owns backoff, attempt accounting, rescheduling, and transmit
trigger decisions.

## Strategy Responsibilities

### GBN Strategy

`UbGbnRetransStrategy` handles:

- TPNAK processing on the sender
- GBN fast retransmission from the NAK PSN
- RTO retransmission from `SndUna`
- receiver-side out-of-order handling
- repeated TPNAK suppression
- clearing TPNAK suppression after the receive gap closes

It should not build full ACK packets. It should return a receive decision that
asks transport to queue TPACK or TPNAK.

### Selective Strategy

`UbSelectiveRetransStrategy` handles:

- retaining sent packet copies for retransmission
- TPSACK processing on the sender
- cumulative ACK updates from TPACK or TPSACK
- missing PSN collection from SAETPH
- selective retransmission queue management
- duplicate queue suppression
- per-PSN retransmit counters
- sparse retransmission packet selection
- RTO queueing of outstanding unacknowledged PSNs
- selective ACK bitmap construction for receiver responses
- MarkPSN phase transitions

It owns `SentPsnState` and the MarkPSN state machine.

## Attribute Compatibility

External ns-3 attributes should remain on `UbTransportChannel` with the same
names. Their storage moves to `UbRetransController`.

For attributes that previously used direct member accessors, use transport
getter/setter forwarding methods:

```cpp
MakeBooleanAccessor(&UbTransportChannel::SetRetransEnable,
                    &UbTransportChannel::GetRetransEnable)
```

The setter forwards to `m_retrans->SetEnable(...)`; the getter forwards to
`m_retrans->GetEnable()`. Existing config files and command-line overrides keep
working.

## Functions To Move

Move or rewrite these from `ub-transport.cc/.h` into `ub-retrans.cc/.h`:

- `SentPsnState`
- `ResolveSelectiveAckBitmapBits`
- `GetSelectiveAckBitmapBits`
- `GetSelectiveAckBase`
- `BuildSelectiveAckHeader`
- `RetainSentPsn`
- `MarkPsnAcked`
- `AcknowledgeCumulativePsn`
- `AdvanceSendUnaFromAckState`
- `CollectMissingPsnsFromSelectiveAck`
- `GetMissingPsnsFromSelectiveAck`
- `QueueSelectiveRetransmission`
- `CompactSelectiveRetransmissionQueue`
- `HasPendingSelectiveRetransmission`
- `CanSendSelectiveRetransmission`
- `GetNextSelectiveRetransmissionSize`
- `GetNextSelectiveRetransmissionLogicalBytes`
- `PrepareGbnRetransmissionFromPsn`
- `IsSelectiveMarkPsnEnabled`
- `SelectiveAckReportsReceivedAtOrAboveMarkPsn`
- `EnterSelectiveMarkPsnRetransPhase`
- `FinishSelectiveMarkPsnRetransPhaseIfDone`
- `MaybeMarkFirstNewSelectivePacket`
- RTO event scheduling and backoff logic

Keep or create these in `UbTransportChannel` as common helpers:

- data packet generation
- response packet construction and queue insertion
- inbound TA packet tracking
- WQE segment completion
- trace notification helpers
- congestion control object ownership
- port lookup and transmit trigger wrapper

## Error Handling

Unknown retransmission modes should remain assertion failures.

Malformed TPSACK parsing should remain in transport packet parsing because it is
header decoding, not retransmission policy.

Invalid selective ACK bitmap configuration should be checked inside the
controller or selective strategy. If invalid, the receive decision should
suppress TPSACK in the same way current code does, preserving behavior.

Exhausted retransmission attempts should preserve the current assertion behavior
initially. Later work may replace this with the spec-defined TP Channel error
reporting path.

## Testing

Run the existing focused tests around:

- selective receiver TPSACK for receive gap
- selective receiver returning to TPACK after gap closes
- first-packet-loss TPSACK behavior
- duplicate packet TPSACK behavior
- sender TPSACK consumption
- local sink TPSACK dispatch
- default GBN out-of-order silence
- GBN fast TPNAK behavior

Then run the retransmission scenario families:

- `GBN_fast`
- `GBN_unfast`
- `SELE_fast`
- `SELE_unfast`

If new direct unit tests are added, prioritize logic with minimal packet setup:

- selective missing PSN queue deduplication
- MarkPSN phase transitions
- GBN TPNAK-triggered send cursor rollback
- RTO backoff and attempt accounting

## Migration Plan

Implement in small behavior-preserving steps:

1. Add `ub-retrans.h/.cc` and CMake entries with no behavior change.
2. Introduce `UbRetransController` and attribute forwarding while keeping old
   logic active.
3. Move RTO state and timeout handling into the controller.
4. Move GBN TPNAK/RTO logic into `UbGbnRetransStrategy`.
5. Move selective sent-PSN state, retransmission queue, and TPSACK processing
   into `UbSelectiveRetransStrategy`.
6. Move MarkPSN state into `UbSelectiveRetransStrategy`.
7. Simplify `GetNextPacket`, `RecvTpAck`, `RecvDataPacket`, and `ReTxTimeout`
   to common flow plus controller calls.
8. Remove obsolete state and test-only accessors from `UbTransportChannel`, or
   forward test accessors to the controller where tests still need them.

## Risks

The highest-risk areas are:

- ns-3 attribute initialization order versus controller construction
- packet copy lifetime for selective retransmission
- RTO timer cancellation during flow completion and object disposal
- preserving congestion-control callback timing
- preserving trace output formatting and packet type classification
- test-only accessors that currently read private transport state

Mitigation: keep public attributes and trace names stable, move one behavior
group at a time, and run focused tests after each migration phase.
