// SPDX-License-Identifier: GPL-2.0-only
#include "ns3/ub-retrans.h"

namespace ns3 {

UbRetransController::UbRetransController(UbTransportChannel& transport)
    : m_transport(transport)
{
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

} // namespace ns3
