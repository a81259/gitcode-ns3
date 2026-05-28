// SPDX-License-Identifier: GPL-2.0-only
#include "ns3/ub-retrans.h"

#include "ns3/assert.h"
#include "ns3/simulator.h"
#include "ns3/ub-transport.h"

#include <algorithm>
#include <array>

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

UbSelectiveRetransStrategy::UbSelectiveRetransStrategy(UbRetransController& controller)
    : m_controller(controller)
{
}

void
UbSelectiveRetransStrategy::RetainSentPsn(uint64_t psn,
                                          Ptr<Packet> packet,
                                          uint32_t payloadBytes,
                                          uint32_t logicalBytes,
                                          Ptr<UbWqeSegment> segment)
{
    SentPsnState& state = m_sentPsnState[psn];
    state.packet = packet != nullptr ? packet->Copy() : nullptr;
    state.payloadBytes = payloadBytes;
    state.logicalBytes = logicalBytes;
    state.segment = segment;
    state.acknowledged = false;
    state.selectivelyReportedMissing = false;
    state.retransmitPending = false;
    state.retransmitCount = 0;
}

void
UbSelectiveRetransStrategy::MarkPsnAcked(uint64_t psn)
{
    auto it = m_sentPsnState.find(psn);
    if (it == m_sentPsnState.end()) {
        return;
    }
    it->second.acknowledged = true;
    it->second.selectivelyReportedMissing = false;
    it->second.retransmitPending = false;
}

void
UbSelectiveRetransStrategy::AcknowledgeCumulativePsn(uint64_t ackPsn)
{
    UbTransportChannel& transport = m_controller.GetTransport();
    for (uint64_t psn = transport.GetPsnSndUna(); psn <= ackPsn; ++psn) {
        MarkPsnAcked(psn);
        if (psn == UINT64_MAX) {
            break;
        }
    }
    if (ackPsn + 1 > transport.GetPsnSndUna()) {
        transport.SetPsnSndUna(ackPsn + 1);
    }
    RetireAckedStateBeforeSendUna();
}

void
UbSelectiveRetransStrategy::AdvanceSendUnaFromAckState()
{
    UbTransportChannel& transport = m_controller.GetTransport();
    while (true) {
        auto it = m_sentPsnState.find(transport.GetPsnSndUna());
        if (it == m_sentPsnState.end() || !it->second.acknowledged) {
            break;
        }
        m_sentPsnState.erase(it);
        transport.SetPsnSndUna(transport.GetPsnSndUna() + 1);
    }
}

std::vector<uint64_t>
UbSelectiveRetransStrategy::CollectMissingPsnsFromSelectiveAck(const UbTransportHeader& tpHeader,
                                                               const UbSelectiveAckExtTph& saetph)
{
    const uint64_t ackBase = tpHeader.GetPsn();
    const uint32_t bitmapBits = saetph.GetBitmapBitCount();
    const uint64_t representedEnd = ackBase + bitmapBits - 1;
    const uint64_t lastCandidate = std::min<uint64_t>(saetph.GetMaxRcvPsn(), representedEnd);
    const bool baseIsMissingEvidence = ackBase == 0 && !saetph.GetBitmapBit(0);
    uint64_t firstCandidate = baseIsMissingEvidence ? 0 : ackBase + 1;
    std::vector<uint64_t> missingPsns;

    for (uint64_t psn = ackBase; psn <= lastCandidate; ++psn) {
        const uint32_t offset = static_cast<uint32_t>(psn - ackBase);
        if (saetph.GetBitmapBit(offset)) {
            MarkPsnAcked(psn);
        }
        if (psn == UINT64_MAX) {
            break;
        }
    }

    for (uint64_t psn = firstCandidate; psn <= lastCandidate; ++psn) {
        const uint32_t offset = static_cast<uint32_t>(psn - ackBase);
        if (saetph.GetBitmapBit(offset)) {
            if (psn == UINT64_MAX) {
                break;
            }
            continue;
        }

        auto it = m_sentPsnState.find(psn);
        if (it != m_sentPsnState.end() && !it->second.acknowledged &&
            !it->second.selectivelyReportedMissing)
        {
            it->second.selectivelyReportedMissing = true;
            missingPsns.push_back(psn);
        }
        if (psn == UINT64_MAX) {
            break;
        }
    }
    return missingPsns;
}

std::vector<uint64_t>
UbSelectiveRetransStrategy::GetMissingPsnsFromSelectiveAck(const UbTransportHeader& tpHeader,
                                                           const UbSelectiveAckExtTph& saetph) const
{
    const uint64_t ackBase = tpHeader.GetPsn();
    const uint32_t bitmapBits = saetph.GetBitmapBitCount();
    const uint64_t representedEnd = ackBase + bitmapBits - 1;
    const uint64_t lastCandidate = std::min<uint64_t>(saetph.GetMaxRcvPsn(), representedEnd);
    const bool baseIsMissingEvidence = ackBase == 0 && !saetph.GetBitmapBit(0);
    const uint64_t firstCandidate = baseIsMissingEvidence ? 0 : ackBase + 1;
    std::vector<uint64_t> missingPsns;

    for (uint64_t psn = firstCandidate; psn <= lastCandidate; ++psn) {
        const uint32_t offset = static_cast<uint32_t>(psn - ackBase);
        if (!saetph.GetBitmapBit(offset)) {
            missingPsns.push_back(psn);
        }
        if (psn == UINT64_MAX) {
            break;
        }
    }
    return missingPsns;
}

bool
UbSelectiveRetransStrategy::QueueRetransmission(uint64_t psn)
{
    auto it = m_sentPsnState.find(psn);
    if (it == m_sentPsnState.end() || it->second.acknowledged || it->second.retransmitPending) {
        return false;
    }
    it->second.retransmitPending = true;
    m_selectiveRetransmitQ.push_back(psn);
    return true;
}

void
UbSelectiveRetransStrategy::CompactRetransmissionQueue()
{
    std::deque<uint64_t> liveQueue;
    for (uint64_t psn : m_selectiveRetransmitQ) {
        auto it = m_sentPsnState.find(psn);
        if (it != m_sentPsnState.end() && !it->second.acknowledged &&
            it->second.retransmitPending && it->second.packet != nullptr)
        {
            liveQueue.push_back(psn);
        }
    }
    m_selectiveRetransmitQ.swap(liveQueue);
}

bool
UbSelectiveRetransStrategy::HasPendingRetransmission() const
{
    for (uint64_t psn : m_selectiveRetransmitQ) {
        auto it = m_sentPsnState.find(psn);
        if (it != m_sentPsnState.end() && !it->second.acknowledged && it->second.packet != nullptr) {
            return true;
        }
    }
    return false;
}

bool
UbSelectiveRetransStrategy::CanSendRetransmission() const
{
    if (m_controller.GetRetransmissionMode() != UbRetransmissionMode::SELECTIVE) {
        return false;
    }
    if (!HasPendingRetransmission()) {
        return false;
    }
    return !m_controller.GetTransport().IsSelectiveMarkPsnEnabledForRetrans() ||
           m_controller.GetTransport().IsSelectiveMarkPsnRetransPhaseActiveForRetrans();
}

uint32_t
UbSelectiveRetransStrategy::GetNextRetransmissionSize() const
{
    for (uint64_t psn : m_selectiveRetransmitQ) {
        auto it = m_sentPsnState.find(psn);
        if (it != m_sentPsnState.end() && !it->second.acknowledged && it->second.packet != nullptr) {
            return it->second.packet->GetSize();
        }
    }
    return 0;
}

uint32_t
UbSelectiveRetransStrategy::GetNextRetransmissionLogicalBytes() const
{
    for (uint64_t psn : m_selectiveRetransmitQ) {
        auto it = m_sentPsnState.find(psn);
        if (it != m_sentPsnState.end() && !it->second.acknowledged && it->second.packet != nullptr) {
            return it->second.logicalBytes;
        }
    }
    return 0;
}

uint32_t
UbSelectiveRetransStrategy::GetRetainedLogicalBytes(uint64_t psn) const
{
    auto it = m_sentPsnState.find(psn);
    return it == m_sentPsnState.end() ? 0 : it->second.logicalBytes;
}

Ptr<Packet>
UbSelectiveRetransStrategy::TryGetNextRetransmissionPacket()
{
    UbTransportChannel& transport = m_controller.GetTransport();
    while (CanSendRetransmission()) {
        const uint64_t psn = m_selectiveRetransmitQ.front();
        auto it = m_sentPsnState.find(psn);
        if (it == m_sentPsnState.end() || it->second.acknowledged || it->second.packet == nullptr) {
            m_selectiveRetransmitQ.pop_front();
            if (transport.IsSelectiveMarkPsnEnabledForRetrans()) {
                transport.FinishSelectiveMarkPsnRetransPhaseIfDoneForRetrans();
            }
            continue;
        }
        const uint32_t logicalBytes = it->second.logicalBytes == 0 ? UB_MTU_BYTE : it->second.logicalBytes;
        if (transport.IsCcLimitedForRetransmission(logicalBytes)) {
            transport.SetSendWindowLimited(true);
            return nullptr;
        }
        m_selectiveRetransmitQ.pop_front();
        it->second.retransmitPending = false;
        if (transport.IsSelectiveMarkPsnEnabledForRetrans() && it->second.retransmitCount == 0) {
            transport.RecordFirstSelectiveRetransmissionForRetrans(psn);
        }
        it->second.retransmitCount++;
        transport.OnSelectiveRetransmissionPacketSent(psn, logicalBytes, it->second.payloadBytes);
        Ptr<Packet> retransmission = it->second.packet->Copy();
        if (transport.IsSelectiveMarkPsnEnabledForRetrans()) {
            transport.FinishSelectiveMarkPsnRetransPhaseIfDoneForRetrans();
        }
        return retransmission;
    }
    if (transport.IsSelectiveMarkPsnEnabledForRetrans()) {
        transport.FinishSelectiveMarkPsnRetransPhaseIfDoneForRetrans();
    }
    return nullptr;
}

UbRetransTimeoutResult
UbSelectiveRetransStrategy::OnTimeout()
{
    UbRetransTimeoutResult result;
    if (m_controller.GetRetransmissionMode() != UbRetransmissionMode::SELECTIVE) {
        return result;
    }

    UbTransportChannel& transport = m_controller.GetTransport();
    transport.EnterSelectiveMarkPsnRetransPhaseForRetrans();
    for (auto& [psn, state] : m_sentPsnState) {
        if (!state.acknowledged && !state.retransmitPending) {
            state.retransmitPending = true;
            m_selectiveRetransmitQ.push_back(psn);
        }
    }
    result.triggerTransmit = true;
    return result;
}

UbRetransAckResult
UbSelectiveRetransStrategy::OnTransportResponse(const UbTransportHeader& tpHeader,
                                                TpOpcode opcode,
                                                const UbSelectiveAckExtTph& saetph,
                                                const UbCongestionExtTph* cetph)
{
    UbRetransAckResult result;
    if (m_controller.GetRetransmissionMode() != UbRetransmissionMode::SELECTIVE) {
        return result;
    }

    UbTransportChannel& transport = m_controller.GetTransport();
    result.previousSndUna = transport.GetPsnSndUna();
    const std::vector<uint64_t> allMissingPsns = GetMissingPsnsFromSelectiveAck(tpHeader, saetph);
    if (transport.SelectiveAckReportsReceivedAtOrAboveMarkPsnForRetrans(tpHeader, saetph)) {
        transport.EnterSelectiveMarkPsnRetransPhaseForRetrans();
    }
    if (saetph.GetBitmapBit(0)) {
        AcknowledgeCumulativePsn(tpHeader.GetPsn());
    }
    std::vector<uint64_t> missingPsns = CollectMissingPsnsFromSelectiveAck(tpHeader, saetph);
    uint32_t retransmitBytes = 0;
    for (uint64_t psn : missingPsns) {
        retransmitBytes += GetRetainedLogicalBytes(psn);
    }
    transport.OnSenderSelectiveAck(opcode, tpHeader.GetPsn(), saetph, cetph, retransmitBytes);
    bool queuedFastRetransmission = false;
    if (m_controller.GetFastRetransEnable()) {
        const std::vector<uint64_t>& candidatePsns =
            transport.IsSelectiveMarkPsnEnabledForRetrans() ? allMissingPsns : missingPsns;
        for (uint64_t psn : candidatePsns) {
            if (transport.IsSelectiveMarkPsnEnabledForRetrans() &&
                !transport.IsSelectiveMarkPsnRetransPhaseActiveForRetrans()) {
                continue;
            }
            queuedFastRetransmission = QueueRetransmission(psn) || queuedFastRetransmission;
        }
    }
    AdvanceSendUnaFromAckState();
    RetireAckedStateBeforeSendUna();
    CompactRetransmissionQueue();
    result.newSndUna = transport.GetPsnSndUna();
    result.ackAdvanced = result.newSndUna > result.previousSndUna;
    result.triggerTransmit = queuedFastRetransmission && CanSendRetransmission() &&
                             !transport.IsCcLimitedForRetransmission(GetNextRetransmissionLogicalBytes());
    return result;
}

UbRetransAckResult
UbSelectiveRetransStrategy::OnCumulativeAck(const UbTransportHeader& tpHeader)
{
    UbRetransAckResult result;
    if (m_controller.GetRetransmissionMode() != UbRetransmissionMode::SELECTIVE) {
        return result;
    }

    UbTransportChannel& transport = m_controller.GetTransport();
    result.previousSndUna = transport.GetPsnSndUna();
    AcknowledgeCumulativePsn(tpHeader.GetPsn());
    AdvanceSendUnaFromAckState();
    CompactRetransmissionQueue();
    result.newSndUna = transport.GetPsnSndUna();
    result.ackAdvanced = result.newSndUna > result.previousSndUna;
    return result;
}

bool
UbSelectiveRetransStrategy::ResolveSelectiveAckBitmapBits(uint32_t& bits) const
{
    const uint32_t configuredBits = m_controller.GetSelectiveAckBitmapBitsConfig();
    if (configuredBits != 0)
    {
        if (!UbSelectiveAckExtTph::IsSupportedBitmapBitCount(configuredBits))
        {
            return false;
        }
        bits = configuredBits;
        return true;
    }

    const uint32_t usefulWindow =
        std::min<uint32_t>(m_controller.GetTransport().GetPsnOooThresholdForRetrans(), 1024);
    if (usefulWindow == 0)
    {
        return false;
    }

    const std::array<uint32_t, 5> supportedBits = {64, 128, 256, 512, 1024};
    for (uint32_t candidate : supportedBits)
    {
        if (candidate >= usefulWindow)
        {
            bits = candidate;
            return true;
        }
    }

    return false;
}

uint32_t
UbSelectiveRetransStrategy::GetSelectiveAckBitmapBits() const
{
    uint32_t bits = 0;
    const bool resolved = ResolveSelectiveAckBitmapBits(bits);
    NS_ASSERT_MSG(resolved, "Invalid selective ACK bitmap configuration");
    return bits;
}

uint64_t
UbSelectiveRetransStrategy::GetSelectiveAckBase() const
{
    return m_controller.GetTransport().GetCumulativeAckPsnForRetrans();
}

UbSelectiveAckExtTph
UbSelectiveRetransStrategy::BuildSelectiveAckHeader(uint64_t ackBase) const
{
    const UbTransportChannel& transport = m_controller.GetTransport();
    UbSelectiveAckExtTph header;
    header.SetBitmapBitCount(GetSelectiveAckBitmapBits());
    header.SetMaxRcvPsn(static_cast<uint32_t>(transport.GetMaxRcvPsnForRetrans()));

    const uint32_t bitmapBits = header.GetBitmapBitCount();
    const uint64_t maxEvidencePsn =
        std::min<uint64_t>(transport.GetMaxRcvPsnForRetrans(), ackBase + bitmapBits - 1);
    for (uint64_t psn = ackBase; psn <= maxEvidencePsn; ++psn)
    {
        if (psn < transport.GetPsnRecvNxt() || transport.ReceiveWindowContainsForRetrans(psn))
        {
            header.SetBitmapBit(static_cast<uint32_t>(psn - ackBase), true);
        }
        if (psn == UINT64_MAX)
        {
            break;
        }
    }
    return header;
}

UbRetransReceiveDecision
UbSelectiveRetransStrategy::BuildReceiveDecisionForCurrentState() const
{
    const UbTransportChannel& transport = m_controller.GetTransport();
    UbRetransReceiveDecision decision;
    decision.shouldAck = true;

    if (!transport.HasReceiveGapForRetrans())
    {
        decision.responsePsn = transport.GetCumulativeAckPsnForRetrans();
        decision.responseOpcode = transport.GetResponseOpcodeForRetrans(false);
        return decision;
    }

    uint32_t selectiveAckBits = 0;
    decision.selectiveAck = true;
    decision.responsePsn = GetSelectiveAckBase();
    if (!ResolveSelectiveAckBitmapBits(selectiveAckBits))
    {
        decision.suppressResponse = true;
        return decision;
    }

    decision.responseOpcode = transport.GetResponseOpcodeForRetrans(true);
    decision.selectiveAckHeader = BuildSelectiveAckHeader(decision.responsePsn);
    return decision;
}

void
UbSelectiveRetransStrategy::RetireAckedStateBeforeSendUna()
{
    const uint64_t sndUna = m_controller.GetTransport().GetPsnSndUna();
    for (auto it = m_sentPsnState.begin(); it != m_sentPsnState.end();) {
        if (it->first < sndUna && it->second.acknowledged) {
            it = m_sentPsnState.erase(it);
        } else {
            ++it;
        }
    }
}

uint32_t
UbSelectiveRetransStrategy::GetPendingRetransmissionCountForTest() const
{
    uint32_t count = 0;
    for (uint64_t psn : m_selectiveRetransmitQ) {
        auto it = m_sentPsnState.find(psn);
        if (it != m_sentPsnState.end() && !it->second.acknowledged && it->second.packet != nullptr) {
            ++count;
        }
    }
    return count;
}

uint32_t
UbSelectiveRetransStrategy::GetRawRetransmissionQueueCountForTest() const
{
    return static_cast<uint32_t>(m_selectiveRetransmitQ.size());
}

bool
UbSelectiveRetransStrategy::WasPsnSelectivelyReportedMissingForTest(uint64_t psn) const
{
    auto it = m_sentPsnState.find(psn);
    return it != m_sentPsnState.end() && it->second.selectivelyReportedMissing;
}

bool
UbSelectiveRetransStrategy::HasRetainedPsnForTest(uint64_t psn) const
{
    return m_sentPsnState.find(psn) != m_sentPsnState.end();
}

uint32_t
UbSelectiveRetransStrategy::GetPsnRetransmitCountForTest(uint64_t psn) const
{
    auto it = m_sentPsnState.find(psn);
    return it == m_sentPsnState.end() ? 0 : it->second.retransmitCount;
}

void
UbSelectiveRetransStrategy::Clear()
{
    m_sentPsnState.clear();
    m_selectiveRetransmitQ.clear();
}

UbRetransController::UbRetransController(UbTransportChannel& transport)
    : m_transport(transport)
{
    m_gbn = std::make_unique<UbGbnRetransStrategy>(*this);
    m_selective = std::make_unique<UbSelectiveRetransStrategy>(*this);
}

UbRetransController::~UbRetransController()
{
    CancelTimer();
    ClearRetainedState();
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
    if (m_retransmissionMode == UbRetransmissionMode::SELECTIVE) {
        return m_selective->OnTimeout();
    }
    NS_ASSERT_MSG(false, "Unknown retransmission mode.");
    return {};
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
    UbRetransAckResult result;
    if (opcode == TpOpcode::TP_OPCODE_NAK_WITHOUT_CETPH) {
        result.triggerTransmit = m_gbn->HandleTpNak(tph.GetPsn());
    } else if (m_retransmissionMode == UbRetransmissionMode::SELECTIVE &&
               (opcode == TpOpcode::TP_OPCODE_SACK_WITHOUT_CETPH ||
                opcode == TpOpcode::TP_OPCODE_SACK_WITH_CETPH)) {
        NS_ASSERT_MSG(saetph != nullptr, "SELECTIVE TPSACK processing requires SAETPH.");
        result = m_selective->OnTransportResponse(tph, opcode, *saetph, cetph);
    } else if (m_retransmissionMode == UbRetransmissionMode::SELECTIVE &&
               (opcode == TpOpcode::TP_OPCODE_ACK_WITHOUT_CETPH ||
                opcode == TpOpcode::TP_OPCODE_ACK_WITH_CETPH)) {
        result = m_selective->OnCumulativeAck(tph);
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

bool
UbRetransController::ResolveSelectiveAckBitmapBits(uint32_t& bits) const
{
    return m_selective->ResolveSelectiveAckBitmapBits(bits);
}

UbRetransReceiveDecision
UbRetransController::BuildReceiveDecisionForCurrentState() const
{
    if (m_retransmissionMode == UbRetransmissionMode::SELECTIVE)
    {
        return m_selective->BuildReceiveDecisionForCurrentState();
    }

    UbRetransReceiveDecision decision;
    decision.shouldAck = true;
    decision.responsePsn = m_transport.GetCumulativeAckPsnForRetrans();
    decision.responseOpcode = m_transport.GetResponseOpcodeForRetrans(false);
    return decision;
}

void
UbRetransController::OnNewDataPacketSent(uint64_t psn,
                                         Ptr<Packet> packet,
                                         uint32_t payloadBytes,
                                         uint32_t logicalBytes,
                                         Ptr<UbWqeSegment> segment)
{
    if (m_retransmissionMode == UbRetransmissionMode::SELECTIVE) {
        m_selective->RetainSentPsn(psn, packet, payloadBytes, logicalBytes, segment);
    }
}

Ptr<Packet>
UbRetransController::TryGetNextRetransmissionPacket()
{
    if (m_retransmissionMode == UbRetransmissionMode::SELECTIVE) {
        return m_selective->TryGetNextRetransmissionPacket();
    }
    return nullptr;
}

bool
UbRetransController::HasPendingSelectiveRetransmission() const
{
    return m_retransmissionMode == UbRetransmissionMode::SELECTIVE &&
           m_selective->HasPendingRetransmission();
}

bool
UbRetransController::CanSendSelectiveRetransmission() const
{
    return m_retransmissionMode == UbRetransmissionMode::SELECTIVE &&
           m_selective->CanSendRetransmission();
}

uint32_t
UbRetransController::GetNextSelectiveRetransmissionSize() const
{
    if (m_retransmissionMode != UbRetransmissionMode::SELECTIVE) {
        return 0;
    }
    return m_selective->GetNextRetransmissionSize();
}

uint32_t
UbRetransController::GetNextSelectiveRetransmissionLogicalBytes() const
{
    if (m_retransmissionMode != UbRetransmissionMode::SELECTIVE) {
        return 0;
    }
    return m_selective->GetNextRetransmissionLogicalBytes();
}

uint32_t
UbRetransController::GetPendingSelectiveRetransmissionCountForTest() const
{
    return m_selective->GetPendingRetransmissionCountForTest();
}

uint32_t
UbRetransController::GetRawSelectiveRetransmissionQueueCountForTest() const
{
    return m_selective->GetRawRetransmissionQueueCountForTest();
}

bool
UbRetransController::WasPsnSelectivelyReportedMissingForTest(uint64_t psn) const
{
    return m_selective->WasPsnSelectivelyReportedMissingForTest(psn);
}

bool
UbRetransController::HasRetainedPsnForTest(uint64_t psn) const
{
    return m_selective->HasRetainedPsnForTest(psn);
}

uint32_t
UbRetransController::GetPsnRetransmitCountForTest(uint64_t psn) const
{
    return m_selective->GetPsnRetransmitCountForTest(psn);
}

void
UbRetransController::ClearRetainedState()
{
    if (m_selective != nullptr) {
        m_selective->Clear();
    }
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
