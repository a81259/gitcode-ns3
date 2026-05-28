// SPDX-License-Identifier: GPL-2.0-only
#include "ns3/ub-retrans.h"

#include "ns3/assert.h"
#include "ns3/simulator.h"
#include "ns3/ub-transport.h"

namespace ns3 {

UbGbnRetransStrategy::UbGbnRetransStrategy(UbRetransController& controller)
    : m_controller(controller)
{
}

void
UbGbnRetransStrategy::PrepareRetransmissionFromPsn(uint64_t psn)
{
    UbTransportChannel& transport = m_controller.GetTransport();
    if (psn < transport.GetPsnSndUna() || psn >= transport.GetPsnSndNxt()) {
        return;
    }

    transport.SetPsnSndNxt(psn);
    transport.ResetSegmentSendProgressFromPsn(psn);
}

bool
UbGbnRetransStrategy::HandleTpNak(uint64_t nakPsn)
{
    if (m_controller.GetRetransmissionMode() != UbRetransmissionMode::GBN ||
        !m_controller.GetFastRetransEnable()) {
        return false;
    }

    const UbTransportChannel& transport = m_controller.GetTransport();
    if (nakPsn < transport.GetPsnSndUna() || nakPsn >= transport.GetPsnSndNxt()) {
        return false;
    }

    PrepareRetransmissionFromPsn(nakPsn);
    return true;
}

UbRetransReceiveDecision
UbGbnRetransStrategy::OnDataPacketReceived(uint64_t psn)
{
    UbRetransReceiveDecision decision;
    if (m_controller.GetRetransmissionMode() != UbRetransmissionMode::GBN ||
        !m_controller.GetFastRetransEnable()) {
        return decision;
    }

    const uint64_t nakPsn = m_controller.GetTransport().GetPsnRecvNxt();
    if (psn <= nakPsn) {
        return decision;
    }
    if (m_lastNakPsn == nakPsn) {
        decision.suppressResponse = true;
        decision.responsePsn = nakPsn;
        return decision;
    }

    m_lastNakPsn = nakPsn;
    decision.shouldNak = true;
    decision.responsePsn = nakPsn;
    decision.responseOpcode = TpOpcode::TP_OPCODE_NAK_WITHOUT_CETPH;
    return decision;
}

UbRetransTimeoutResult
UbGbnRetransStrategy::OnTimeout()
{
    UbRetransTimeoutResult result;
    if (m_controller.GetRetransmissionMode() != UbRetransmissionMode::GBN) {
        return result;
    }

    PrepareRetransmissionFromPsn(m_controller.GetTransport().GetPsnSndUna());
    result.triggerTransmit = true;
    return result;
}

void
UbGbnRetransStrategy::ClearNakSuppressionIfGapClosed(uint64_t recvNext)
{
    if (m_lastNakPsn != std::numeric_limits<uint64_t>::max() && recvNext > m_lastNakPsn) {
        m_lastNakPsn = std::numeric_limits<uint64_t>::max();
    }
}

UbRetransController::UbRetransController(UbTransportChannel& transport)
    : m_transport(transport)
{
    m_gbn = std::make_unique<UbGbnRetransStrategy>(*this);
}

UbRetransController::~UbRetransController()
{
    CancelTimer();
}

void
UbRetransController::SetInitialRto(Time rto)
{
    m_initialRto = rto;
    m_rto = rto;
}

Time
UbRetransController::GetInitialRto() const
{
    return m_initialRto;
}

void
UbRetransController::SetCurrentRto(Time rto)
{
    m_rto = rto;
}

Time
UbRetransController::GetCurrentRto() const
{
    return m_rto;
}

void
UbRetransController::SetMaxRetransAttempts(uint16_t attempts)
{
    m_maxRetransAttempts = attempts;
    m_retransAttemptsLeft = attempts;
}

uint16_t
UbRetransController::GetMaxRetransAttempts() const
{
    return m_maxRetransAttempts;
}

void
UbRetransController::SetRetransAttemptsLeft(uint16_t attempts)
{
    m_retransAttemptsLeft = attempts;
}

uint16_t
UbRetransController::GetRetransAttemptsLeft() const
{
    return m_retransAttemptsLeft;
}

void
UbRetransController::SetRetransExponentFactor(uint16_t factor)
{
    m_retransExponentFactor = factor;
}

uint16_t
UbRetransController::GetRetransExponentFactor() const
{
    return m_retransExponentFactor;
}

void
UbRetransController::SetRetransmissionMode(UbRetransmissionMode mode)
{
    m_retransmissionMode = mode;
}

UbRetransmissionMode
UbRetransController::GetRetransmissionMode() const
{
    return m_retransmissionMode;
}

void
UbRetransController::SetSelectiveAckBitmapBits(uint32_t bits)
{
    m_selectiveAckBitmapBits = bits;
}

uint32_t
UbRetransController::GetSelectiveAckBitmapBitsConfig() const
{
    return m_selectiveAckBitmapBits;
}

void
UbRetransController::SetFastRetransEnable(bool enable)
{
    m_enableFastRetrans = enable;
}

bool
UbRetransController::GetFastRetransEnable() const
{
    return m_enableFastRetrans;
}

void
UbRetransController::SetSelectiveMarkPsnEnable(bool enable)
{
    m_enableSelectiveMarkPsn = enable;
}

bool
UbRetransController::GetSelectiveMarkPsnEnable() const
{
    return m_enableSelectiveMarkPsn;
}

void
UbRetransController::ScheduleTimeout()
{
    m_retransEvent = Simulator::Schedule(m_rto, &UbTransportChannel::ReTxTimeout, &m_transport);
}

void
UbRetransController::StartTimerIfNeeded()
{
    if (!m_retransEvent.IsExpired())
    {
        return;
    }

    m_rto = m_initialRto;
    ScheduleTimeout();
}

void
UbRetransController::RestartTimerAfterAckProgress()
{
    m_rto = m_initialRto;
    m_retransAttemptsLeft = m_maxRetransAttempts;
    m_retransEvent.Cancel();
    ScheduleTimeout();
}

void
UbRetransController::CancelTimer()
{
    m_retransEvent.Cancel();
}

UbRetransTimeoutResult
UbRetransController::OnTimeout()
{
    m_retransAttemptsLeft--;
    uint64_t rto = m_rto.GetNanoSeconds();
    rto = rto << m_retransExponentFactor;
    m_rto = NanoSeconds(rto);
    NS_ASSERT_MSG(m_retransAttemptsLeft > 0, "Avaliable retransmission attempts exhausted.");
    ScheduleTimeout();
    if (m_retransmissionMode == UbRetransmissionMode::GBN) {
        return m_gbn->OnTimeout();
    }
    UbRetransTimeoutResult result;
    result.triggerTransmit = true;
    return result;
}

bool
UbRetransController::HasTimerRunning() const
{
    return !m_retransEvent.IsExpired();
}

UbRetransAckResult
UbRetransController::OnTransportResponse(const UbTransportHeader& tph,
                                         TpOpcode opcode,
                                         const UbSelectiveAckExtTph* saetph,
                                         const UbCongestionExtTph* cetph)
{
    (void)saetph;
    (void)cetph;
    UbRetransAckResult result;
    if (opcode == TpOpcode::TP_OPCODE_NAK_WITHOUT_CETPH) {
        result.triggerTransmit = m_gbn->HandleTpNak(tph.GetPsn());
    }
    return result;
}

UbRetransReceiveDecision
UbRetransController::OnDataPacketReceived(uint64_t psn)
{
    if (m_retransmissionMode == UbRetransmissionMode::GBN) {
        return m_gbn->OnDataPacketReceived(psn);
    }
    return {};
}

void
UbRetransController::ClearNakSuppressionIfGapClosed(uint64_t recvNext)
{
    m_gbn->ClearNakSuppressionIfGapClosed(recvNext);
}

UbTransportChannel&
UbRetransController::GetTransport()
{
    return m_transport;
}

const UbTransportChannel&
UbRetransController::GetTransport() const
{
    return m_transport;
}

} // namespace ns3
