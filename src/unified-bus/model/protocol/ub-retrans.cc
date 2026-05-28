// SPDX-License-Identifier: GPL-2.0-only
#include "ns3/ub-retrans.h"

#include "ns3/assert.h"
#include "ns3/simulator.h"
#include "ns3/ub-transport.h"

namespace ns3 {

UbRetransController::UbRetransController(UbTransportChannel& transport)
    : m_transport(transport)
{
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
    UbRetransTimeoutResult result;
    result.triggerTransmit = true;
    return result;
}

bool
UbRetransController::HasTimerRunning() const
{
    return !m_retransEvent.IsExpired();
}

} // namespace ns3
