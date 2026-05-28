// SPDX-License-Identifier: GPL-2.0-only
#ifndef UB_RETRANS_H
#define UB_RETRANS_H

#include "ns3/event-id.h"
#include "ns3/nstime.h"
#include "ns3/ub-datatype.h"
#include "ns3/ub-header.h"

#include <cstdint>
#include <optional>

namespace ns3 {

class UbTransportChannel;

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
    bool suppressResponse{false};
    uint64_t responsePsn{0};
    TpOpcode responseOpcode{TpOpcode::TP_OPCODE_ACK_WITHOUT_CETPH};
    std::optional<UbSelectiveAckExtTph> selectiveAckHeader;
};

struct UbRetransTimeoutResult
{
    bool triggerTransmit{false};
};

class UbRetransStrategy
{
public:
    virtual ~UbRetransStrategy() = default;
};

class UbRetransController
{
public:
    explicit UbRetransController(UbTransportChannel& transport);
    ~UbRetransController();

    void SetInitialRto(Time rto);
    Time GetInitialRto() const;

    void SetCurrentRto(Time rto);
    Time GetCurrentRto() const;

    void SetMaxRetransAttempts(uint16_t attempts);
    uint16_t GetMaxRetransAttempts() const;

    void SetRetransAttemptsLeft(uint16_t attempts);
    uint16_t GetRetransAttemptsLeft() const;

    void SetRetransExponentFactor(uint16_t factor);
    uint16_t GetRetransExponentFactor() const;

    void SetRetransmissionMode(UbRetransmissionMode mode);
    UbRetransmissionMode GetRetransmissionMode() const;

    void SetSelectiveAckBitmapBits(uint32_t bits);
    uint32_t GetSelectiveAckBitmapBitsConfig() const;

    void SetFastRetransEnable(bool enable);
    bool GetFastRetransEnable() const;

    void SetSelectiveMarkPsnEnable(bool enable);
    bool GetSelectiveMarkPsnEnable() const;

    void StartTimerIfNeeded();
    void RestartTimerAfterAckProgress();
    void CancelTimer();
    UbRetransTimeoutResult OnTimeout();
    bool HasTimerRunning() const;

private:
    void ScheduleTimeout();

    UbTransportChannel& m_transport;
    EventId m_retransEvent{};
    Time m_initialRto;
    Time m_rto;
    uint16_t m_maxRetransAttempts{7};
    uint16_t m_retransAttemptsLeft{7};
    uint16_t m_retransExponentFactor{1};
    UbRetransmissionMode m_retransmissionMode{UbRetransmissionMode::GBN};
    uint32_t m_selectiveAckBitmapBits{0};
    bool m_enableFastRetrans{false};
    bool m_enableSelectiveMarkPsn{false};
};

} // namespace ns3

#endif // UB_RETRANS_H
