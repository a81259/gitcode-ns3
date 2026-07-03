// SPDX-License-Identifier: GPL-2.0-only
#include "ns3/log.h"
#include "ns3/simulator.h"

#include "ns3/ub-datatype.h"
#include "ns3/ub-controller.h"
#include "ns3/ub-routing-process.h"
#include "ns3/ub-transaction.h"
#include "ns3/ub-utils.h"

namespace ns3 {

NS_LOG_COMPONENT_DEFINE("UbTransaction");

NS_OBJECT_ENSURE_REGISTERED(UbTransaction);

TypeId UbTransaction::GetTypeId(void)
{
    static TypeId tid = TypeId("ns3::UbTransaction")
        .SetParent<Object>()
        .SetGroupName("UnifiedBus");
    return tid;
}

UbTransaction::UbTransaction()
{
    NS_LOG_DEBUG("UbTransaction created");
}

UbTransaction::~UbTransaction()
{
}

UbTransaction::UbTransaction(Ptr<Node> node)
{
    m_nodeId = node->GetId();
    m_random = CreateObject<UniformRandomVariable>();
    m_random->SetAttribute("Min", DoubleValue(0.0));
    m_random->SetAttribute("Max", DoubleValue(1.0));
    m_pushWqeSegmentToTpCb = MakeCallback(&UbTransaction::OnScheduleWqeSegmentFinish, this);
}

void UbTransaction::TpInit(Ptr<UbTransportChannel> tp)
{
    uint32_t tpn = tp->GetTpn();
    m_tpnMap[tpn] = tp;
    m_tpRRIndex[tpn] = 0;
    m_tpSchedulingStatus[tpn] = false;
}

void UbTransaction::TpDeinit(uint32_t tpn)
{
    // 删除与该tp绑定的jetty
    m_tpRelatedJetties.erase(tpn);
    for (auto it = m_jettyTpGroup.begin(); it != m_jettyTpGroup.end(); ++it) {
        // 删除所有jetty中该tp的绑定关系
        auto tpIt = std::find(it->second.begin(), it->second.end(), m_tpnMap[tpn]);
        if (tpIt != it->second.end()) {
            it->second.erase(tpIt);
        }
    }
    m_tpnMap.erase(tpn);
    m_tpRRIndex.erase(tpn);
    m_tpSchedulingStatus.erase(tpn);
    m_tpRelatedRemoteRequests.erase(tpn);
}

Ptr<UbFunction> UbTransaction::GetFunction()
{
    return NodeList::GetNode(m_nodeId)->GetObject<UbController>()->GetUbFunction();
}

Ptr<UbJetty> UbTransaction::GetJetty(uint32_t jettyNum)
{
    return GetFunction()->GetJetty(jettyNum);

}

bool UbTransaction::JettyBindTp(uint32_t src, uint32_t dest, uint32_t jettyNum,
                                bool multiPath, std::vector<uint32_t> tpns)
{
    NS_LOG_DEBUG(this);
    Ptr<UbJetty> ubJetty = GetJetty(jettyNum);
    if (ubJetty == nullptr) {
        return false;
    }

    std::vector<Ptr<UbTransportChannel>> ubTransportGroup;

    for (uint32_t i = 0; i < tpns.size(); i++) {
        uint32_t tpn = tpns[i];
        ubTransportGroup.push_back(m_tpnMap[tpn]);
        if (m_tpRelatedJetties.find(tpn) == m_tpRelatedJetties.end()) {
            m_tpRelatedJetties[tpn] = std::vector<Ptr<UbJetty>>();
        }
    }
    // 在事务层模式为ROL时只能开启单路径模式
    if (m_serviceMode[jettyNum] == TransactionServiceMode::ROL) {
        NS_LOG_WARN("ROL, set to single path forced.");
        multiPath = false;
    }
    if (multiPath) {
        NS_LOG_DEBUG("Multiple tp");
        for (uint32_t i = 0; i < ubTransportGroup.size(); i++) {
            if (std::find(m_tpRelatedJetties[tpns[i]].begin(),
                          m_tpRelatedJetties[tpns[i]].end(),
                          ubJetty) == m_tpRelatedJetties[tpns[i]].end()) {
                m_tpRelatedJetties[tpns[i]].push_back(ubJetty);
            }
        }
    } else {
        NS_LOG_DEBUG("Single tp");
        // 根据随机结果选择TP
        int pos = (int)(m_random->GetValue() * ubTransportGroup.size());
        if (std::find(m_tpRelatedJetties[tpns[pos]].begin(),
                      m_tpRelatedJetties[tpns[pos]].end(),
                      ubJetty) == m_tpRelatedJetties[tpns[pos]].end()) {
            m_tpRelatedJetties[tpns[pos]].push_back(ubJetty);
        }
    }

    m_jettyTpGroup[jettyNum] = ubTransportGroup;
    m_jettyDestNode[jettyNum] = dest;
    return true;
}

void UbTransaction::DestroyJettyTpMap(uint32_t jettyNum)
{
    auto itJettyTp = m_jettyTpGroup.find(jettyNum);
    if (itJettyTp != m_jettyTpGroup.end()) {
        // 解除关系
        m_jettyTpGroup.erase(itJettyTp);
        m_jettyTpScheduleIndex.erase(jettyNum);
        m_jettyScheduledWqeId.erase(jettyNum);
        m_jettyPortScheduledSegmentCount.erase(jettyNum);
        m_jettyTpScheduledSegmentCount.erase(jettyNum);
        m_jettyDestNode.erase(jettyNum);
        NS_LOG_DEBUG("Destroyed jetty in m_jettyTpGroup");
    } else {
        NS_LOG_WARN("Jetty Tp map not found for destruction");
    }

    for (auto it = m_tpRelatedJetties.begin(); it != m_tpRelatedJetties.end(); it++) {
        for (auto jettyIt = it->second.begin(); jettyIt != it->second.end();) {
            if ((*jettyIt)->GetJettyNum() == jettyNum) {
                jettyIt = it->second.erase(jettyIt);
            } else {
                ++jettyIt;
            }
        }
    }
}

const std::vector<Ptr<UbTransportChannel>> UbTransaction::GetJettyRelatedTpVec(uint32_t jettyNum)
{
    NS_LOG_DEBUG(this);
    auto it = m_jettyTpGroup.find(jettyNum);
    if (it != m_jettyTpGroup.end()) {
        return it->second;
    }
    NS_LOG_DEBUG("UbTransportChannel vector not found");
    return {};
}

std::vector<Ptr<UbJetty>> UbTransaction::GetTpRelatedJettyVec(uint32_t tpn)
{
    NS_LOG_DEBUG(this);
    auto it = m_tpRelatedJetties.find(tpn);
    if (it != m_tpRelatedJetties.end()) {
        return it->second;
    }
    NS_LOG_DEBUG("UbJetty vector not found");
    return {};
}

void UbTransaction::TriggerScheduleWqeSegment(uint32_t jettyNum)
{
    // 遍历与该jetty绑定的tp，全部进行调度
    auto tpVec = GetJettyRelatedTpVec(jettyNum);
    if (!tpVec.empty()) {
        for (uint32_t i = 0; i < tpVec.size(); i++) {
            Simulator::ScheduleNow(&UbTransaction::ScheduleWqeSegment, this, tpVec[i]);
        }
    }
}

void UbTransaction::ApplyScheduleWqeSegment(Ptr<UbTransportChannel> tp)
{
    Simulator::ScheduleNow(&UbTransaction::ScheduleWqeSegment, this, tp);
}

bool UbTransaction::HasNonUniformSchedulingWeights(const std::vector<Ptr<UbJetty>>& jetties) const
{
    for (const auto& jetty : jetties) {
        if (jetty == nullptr) {
            continue;
        }

        auto groupIt = m_jettyTpGroup.find(jetty->GetJettyNum());
        if (groupIt == m_jettyTpGroup.end()) {
            continue;
        }

        bool hasReferenceWeight = false;
        uint64_t referenceWeight = 1;
        for (const auto& candidateTp : groupIt->second) {
            if (candidateTp == nullptr) {
                continue;
            }

            uint32_t candidateTpn = candidateTp->GetTpn();
            if (m_tpnMap.find(candidateTpn) == m_tpnMap.end()) {
                continue;
            }

            uint64_t candidateWeight = candidateTp->GetSchedulingWeight();
            if (candidateWeight == 0) {
                candidateWeight = 1;
            }

            if (!hasReferenceWeight) {
                referenceWeight = candidateWeight;
                hasReferenceWeight = true;
                continue;
            }

            if (candidateWeight != referenceWeight) {
                return true;
            }
        }
    }

    return false;
}

bool UbTransaction::ScheduleNextLocalWqeSegment(uint32_t jettyNum)
{
    Ptr<UbJetty> jetty = GetJetty(jettyNum);
    if (jetty == nullptr) {
        return false;
    }

    auto groupIt = m_jettyTpGroup.find(jettyNum);
    if (groupIt == m_jettyTpGroup.end() || groupIt->second.empty()) {
        return false;
    }

    uint32_t nextWqeId = 0;
    if (!jetty->PeekNextWqeId(nextWqeId)) {
        return false;
    }
    auto scheduledWqeIt = m_jettyScheduledWqeId.find(jettyNum);
    if (scheduledWqeIt == m_jettyScheduledWqeId.end() || scheduledWqeIt->second != nextWqeId) {
        m_jettyScheduledWqeId[jettyNum] = nextWqeId;
        m_jettyPortScheduledSegmentCount[jettyNum].clear();
        m_jettyTpScheduledSegmentCount[jettyNum].clear();
    }

    auto& tpGroup = groupIt->second;
    auto& tpScheduledBytes = m_jettyTpScheduledSegmentCount[jettyNum];
    auto& portScheduledBytes = m_jettyPortScheduledSegmentCount[jettyNum];
    uint32_t start = m_jettyTpScheduleIndex[jettyNum] % tpGroup.size();

    struct PortCandidate
    {
        uint64_t weight{1};
        uint64_t count{0};
    };
    std::map<uint16_t, PortCandidate> allPortCandidates;
    std::map<uint16_t, PortCandidate> availablePortCandidates;

    auto isKnownTp = [this](const Ptr<UbTransportChannel>& candidateTp) {
        if (candidateTp == nullptr) {
            return false;
        }

        uint32_t tpn = candidateTp->GetTpn();
        return m_tpnMap.find(tpn) != m_tpnMap.end();
    };

    auto isTpAvailable = [this, &isKnownTp](const Ptr<UbTransportChannel>& candidateTp) {
        if (!isKnownTp(candidateTp)) {
            return false;
        }

        uint32_t tpn = candidateTp->GetTpn();
        if (m_tpSchedulingStatus[tpn]) {
            return false;
        }
        if (candidateTp->IsWqeSegmentLimited()) {
            candidateTp->SetTpFullStatus(true);
            return false;
        }
        return candidateTp->GetActiveSendSegmentCount() <= 1;
    };

    auto addPortCandidate = [&portScheduledBytes](std::map<uint16_t, PortCandidate>& candidates,
                                                  const Ptr<UbTransportChannel>& candidateTp) {
        uint16_t outPort = candidateTp->GetSport();
        uint64_t candidateWeight = candidateTp->GetSchedulingWeight();
        if (candidateWeight == 0) {
            candidateWeight = 1;
        }
        auto& portCandidate = candidates[outPort];
        portCandidate.count = portScheduledBytes[outPort];
        portCandidate.weight = std::max(portCandidate.weight, candidateWeight);
    };

    for (uint32_t offset = 0; offset < tpGroup.size(); offset++) {
        uint32_t pos = (start + offset) % tpGroup.size();
        Ptr<UbTransportChannel> candidateTp = tpGroup[pos];
        if (!isKnownTp(candidateTp)) {
            continue;
        }

        addPortCandidate(allPortCandidates, candidateTp);
        if (isTpAvailable(candidateTp)) {
            addPortCandidate(availablePortCandidates, candidateTp);
        }
    }

    if (availablePortCandidates.empty()) {
        return false;
    }

    const uint64_t projectedBytes = std::max<uint64_t>(1, UB_WQE_TA_SEGMENT_BYTE);

    uint32_t destNode = 0;
    auto destIt = m_jettyDestNode.find(jettyNum);
    if (destIt != m_jettyDestNode.end()) {
        destNode = destIt->second;
    }
    uint64_t portTieSeed = (static_cast<uint64_t>(m_nodeId) << 32) ^
                           (static_cast<uint64_t>(destNode) << 16) ^
                           static_cast<uint64_t>(jettyNum);

    auto projectedCompare = [projectedBytes](uint64_t lhsCount,
                                             uint64_t lhsWeight,
                                             uint64_t rhsCount,
                                             uint64_t rhsWeight) {
        long double lhs =
            static_cast<long double>(lhsCount + projectedBytes) / lhsWeight;
        long double rhs =
            static_cast<long double>(rhsCount + projectedBytes) / rhsWeight;
        if (lhs < rhs) {
            return -1;
        }
        if (lhs > rhs) {
            return 1;
        }
        return 0;
    };

    auto projectedBetter = [&projectedCompare](uint64_t lhsCount,
                                               uint64_t lhsWeight,
                                               uint64_t rhsCount,
                                               uint64_t rhsWeight) {
        int cmp = projectedCompare(lhsCount, lhsWeight, rhsCount, rhsWeight);
        if (cmp != 0) {
            return cmp < 0;
        }
        return lhsWeight > rhsWeight;
    };

    auto selectPortCandidate =
        [&projectedBetter, portTieSeed](const std::map<uint16_t, PortCandidate>& candidates,
                                        uint16_t& selectedPort,
                                        PortCandidate& selectedCandidate) {
            if (candidates.empty()) {
                return false;
            }
            bool hasSelectedPort = false;
            std::vector<std::pair<uint16_t, PortCandidate>> orderedCandidates(candidates.begin(),
                                                                              candidates.end());
            uint32_t portTieOffset = portTieSeed % orderedCandidates.size();
            for (uint32_t i = 0; i < orderedCandidates.size(); i++) {
                const auto& [port, candidate] =
                    orderedCandidates[(portTieOffset + i) % orderedCandidates.size()];
                if (!hasSelectedPort ||
                    projectedBetter(candidate.count,
                                    candidate.weight,
                                    selectedCandidate.count,
                                    selectedCandidate.weight)) {
                    selectedPort = port;
                    selectedCandidate = candidate;
                    hasSelectedPort = true;
                }
            }
            return hasSelectedPort;
        };

    uint16_t bestKnownPort = 0;
    PortCandidate bestKnownCandidate;
    selectPortCandidate(allPortCandidates, bestKnownPort, bestKnownCandidate);

    uint16_t selectedPort = 0;
    PortCandidate selectedPortCandidate;
    if (!selectPortCandidate(availablePortCandidates, selectedPort, selectedPortCandidate)) {
        return false;
    }
    if (selectedPort != bestKnownPort &&
        !projectedBetter(selectedPortCandidate.count,
                         selectedPortCandidate.weight,
                         bestKnownCandidate.count,
                         bestKnownCandidate.weight)) {
        return false;
    }

    Ptr<UbWqeSegment> wqeSegment = jetty->GetNextWqeSegment();
    if (wqeSegment == nullptr) {
        return false;
    }
    const uint64_t scheduledBytes = std::max<uint64_t>(1, wqeSegment->GetSize());

    Ptr<UbTransportChannel> selectedTp = nullptr;
    uint32_t selectedPos = start;
    uint32_t selectedTpn = 0;
    uint64_t selectedTpWeight = 1;
    uint64_t selectedTpCount = 0;

    for (uint32_t offset = 0; offset < tpGroup.size(); offset++) {
        uint32_t pos = (start + offset) % tpGroup.size();
        Ptr<UbTransportChannel> candidateTp = tpGroup[pos];
        if (!isTpAvailable(candidateTp) || candidateTp->GetSport() != selectedPort) {
            continue;
        }

        uint32_t tpn = candidateTp->GetTpn();
        uint64_t candidateWeight = candidateTp->GetSchedulingWeight();
        if (candidateWeight == 0) {
            candidateWeight = 1;
        }
        uint64_t candidateCount = tpScheduledBytes[tpn];
        long double candidateLoad =
            static_cast<long double>(candidateCount + scheduledBytes) / candidateWeight;
        long double selectedLoad =
            static_cast<long double>(selectedTpCount + scheduledBytes) / selectedTpWeight;
        if (selectedTp == nullptr ||
            candidateLoad < selectedLoad ||
            (candidateLoad == selectedLoad && candidateWeight > selectedTpWeight)) {
            selectedTp = candidateTp;
            selectedPos = pos;
            selectedTpn = tpn;
            selectedTpWeight = candidateWeight;
            selectedTpCount = candidateCount;
        }
    }

    if (selectedTp == nullptr) {
        return false;
    }

    ValidateUrmaServiceModeOrDie(jettyNum, wqeSegment);
    wqeSegment->SetTpn(selectedTp->GetTpn());
    m_tpSchedulingStatus[selectedTp->GetTpn()] = true;
    portScheduledBytes[selectedPort] += scheduledBytes;
    tpScheduledBytes[selectedTpn] += scheduledBytes;
    m_jettyTpScheduleIndex[jettyNum] = (selectedPos + 1) % tpGroup.size();
    Simulator::ScheduleNow(&UbTransaction::OnScheduleWqeSegmentFinish, this, wqeSegment);
    return true;
}

bool UbTransaction::IsUrmaReadWriteRequest(const Ptr<UbWqeSegment>& segment)
{
    if (segment == nullptr) {
        return false;
    }
    if (segment->GetSegmentKind() != UbTransactionSegmentKind::REQUEST) {
        return false;
    }
    return segment->GetType() == TaOpcode::TA_OPCODE_WRITE ||
           segment->GetType() == TaOpcode::TA_OPCODE_READ;
}

void UbTransaction::ValidateUrmaServiceModeOrDie(uint32_t jettyNum, const Ptr<UbWqeSegment>& segment)
{
    if (!IsUrmaReadWriteRequest(segment)) {
        return;
    }
    TransactionServiceMode mode = GetTransactionServiceMode(jettyNum);
    NS_ABORT_MSG_IF(mode != TransactionServiceMode::ROI,
                    "URMA read/write currently only supports ROI service mode.");
}

void UbTransaction::ScheduleWqeSegment(Ptr<UbTransportChannel> tp)
{
    if (tp == nullptr) {
        NS_LOG_DEBUG("TP not exist, Stop schedule.");
        return;
    }
    uint32_t tpn = tp->GetTpn();
    // 若tpnmap中没有该tp记录，表示该tp对应的traffic已经完成，TP即将删除
    if (m_tpnMap.find(tpn) == m_tpnMap.end()) {
        NS_LOG_DEBUG("TP already delete, WQE finished. Stop schedule.");
        return;
    }
    // 找到tp相关的Jetty
    auto tpRelatedJetties = GetTpRelatedJettyVec(tpn);
    if (UbRoutingProcess::GetDefaultBwWeightedPacketSpray() &&
        HasNonUniformSchedulingWeights(tpRelatedJetties)) {
        for (const auto& jetty : tpRelatedJetties) {
            if (jetty != nullptr) {
                ScheduleNextLocalWqeSegment(jetty->GetJettyNum());
            }
        }
        tpRelatedJetties.clear();
    }

    // 若当前TP正处于调度状态，则结束，否则继续进行，并将状态设置为true
    if (m_tpSchedulingStatus[tpn]) {
        return;
    }
    m_tpSchedulingStatus[tpn] = true;

    // 记录开始轮询的位置， 避免无限循环
    uint32_t jettyCount = tpRelatedJetties.size();
    uint32_t remoteRequestCount = 0;
    auto remoteRequestMapIt = m_tpRelatedRemoteRequests.find(tpn);
    if (remoteRequestMapIt != m_tpRelatedRemoteRequests.end()) {
        remoteRequestCount = remoteRequestMapIt->second.size();
    }
    uint32_t rrCount = jettyCount + remoteRequestCount;

    // 该TP无对应jetty，不进行调度，状态重置
    if (rrCount == 0) {
        m_tpSchedulingStatus[tpn] = false;
        return;
    }

    // 当前TP队列满，不进行调度，状态重置
    if (tp->IsWqeSegmentLimited() ) {
        tp->SetTpFullStatus(true);
        NS_LOG_DEBUG("Full TP");
        // 满队列或满segment
        m_tpSchedulingStatus[tpn] = false;
        return;
    }

    // 浅流水限制的是仍可继续发送的活跃 segment，避免单个 jetty 预取过深。
    if (tp->GetActiveSendSegmentCount() > 1) {
        NS_LOG_DEBUG("tp active send segment count > 1");
        m_tpSchedulingStatus[tpn] = false;
        return;
    }
    // m_tpRRIndex每次更新时都会进行取余操作，不会大于rrCount
    // 只有某个jetty完成后删除，导致rrCount变小时才会出现这种情况。此时重置轮询位置
    if (m_tpRRIndex[tpn] > rrCount) {
        m_tpRRIndex[tpn] = 0;
    }

    Ptr<UbWqeSegment> wqeSegment = nullptr;
    // 从tpRRIndex开始轮询，找到第一个非空且可以拿到wqesegment的jetty，获取wqesegment
    for (uint32_t i = 0; i < rrCount; i++) {
        uint32_t rrIndex = (m_tpRRIndex[tpn] + i) % rrCount;
        if (rrIndex < jettyCount) { // 轮询本地jetty
            // 获取当前jetty
            Ptr<UbJetty> currentJetty = tpRelatedJetties[rrIndex];
            if (currentJetty == nullptr) {
                continue;
            }
            wqeSegment = currentJetty->GetNextWqeSegment();
            if (wqeSegment == nullptr) {
                continue;
            }
            ValidateUrmaServiceModeOrDie(currentJetty->GetJettyNum(), wqeSegment);
        } else { // 轮询remoteRequest
            uint32_t remoteIndex = rrIndex - jettyCount;
            auto remoteIt = m_tpRelatedRemoteRequests.find(tpn);
            if (remoteIt == m_tpRelatedRemoteRequests.end()) {
                continue;
            }
            auto it = remoteIt->second.begin();
            std::advance(it, remoteIndex);
            if (it == remoteIt->second.end()) {
                continue;
            }
            auto& remoteSegments = it->second;
            for (auto vecIt = remoteSegments.begin(); vecIt != remoteSegments.end();) {
                if (*vecIt == nullptr) {
                    vecIt = remoteSegments.erase(vecIt);
                    continue;
                }
                wqeSegment = *vecIt;
                remoteSegments.erase(vecIt);
                break;
            }
            if (wqeSegment == nullptr) {
                continue;
            }
            if (remoteSegments.empty()) {
                remoteIt->second.erase(it);
            }
        }
        if (wqeSegment != nullptr) {
            m_tpRRIndex[tpn] = (rrIndex + 1) % rrCount;
            break;
        }
    }
    if (wqeSegment != nullptr) {
        wqeSegment->SetTpn(tpn);
        Simulator::ScheduleNow(&UbTransaction::OnScheduleWqeSegmentFinish, this, wqeSegment);
    } else {
        m_tpSchedulingStatus[tpn] = false;
    }

}

void UbTransaction::OnScheduleWqeSegmentFinish(Ptr<UbWqeSegment> segment)
{
    Ptr<UbTransportChannel> tp = m_tpnMap[segment->GetTpn()];
    segment->SetTpMsn(tp->GetMsnCnt());
    segment->SetPsnStart(tp->GetPsnCnt());
    tp->UpdatePsnCnt(segment->GetPsnSize());
    tp->UpDateMsnCnt(1);
    tp->PushWqeSegment(segment);
    NS_LOG_INFO("WQE Segment Sends, taskId:" << segment->GetTaskId()
        << "TASSN: "<< segment->GetTaSsn());
    tp->WqeSegmentTriggerPortTransmit(segment);
    // TP调度状态重置
    m_tpSchedulingStatus[segment->GetTpn()] = false;
    ScheduleWqeSegment(tp);
}

bool UbTransaction::ProcessWqeSegmentComplete(Ptr<UbWqeSegment> wqeSegment)
{
    if (wqeSegment == nullptr) {
        return false;
    }

    uint32_t jettyNum = wqeSegment->GetJettyNum();
    uint32_t taSsn = wqeSegment->GetTaSsn();
    if (wqeSegment->GetSegmentKind() == UbTransactionSegmentKind::RESPONSE) {
        jettyNum = wqeSegment->GetOriginJettyNum();
        taSsn = wqeSegment->GetRequestTassn();
    }

    Ptr<UbJetty> jetty = GetJetty(jettyNum);
    if (jetty == nullptr) {
        return false;
    }
    return jetty->ProcessWqeSegmentComplete(taSsn);
}

void UbTransaction::HandleInboundTaUnit(uint32_t localTpn, Ptr<UbWqeSegment> segment)
{
    if (segment == nullptr) {
        return;
    }

    if (segment->GetSegmentKind() == UbTransactionSegmentKind::RESPONSE) {
        CompleteLocalRequestFromResponse(segment);
        return;
    }

    Ptr<UbWqeSegment> response = nullptr;
    if (segment->GetType() == TaOpcode::TA_OPCODE_WRITE) {
        response = ExecuteRemoteWriteAndBuildAck(localTpn, segment);
    } else if (segment->GetType() == TaOpcode::TA_OPCODE_READ) {
        response = ExecuteRemoteReadAndBuildResponse(localTpn, segment);
    } else {
        return;
    }

    if (response == nullptr) {
        return;
    }

    m_tpRelatedRemoteRequests[localTpn][response->GetOriginJettyNum()].push_back(response);
    auto tpIt = m_tpnMap.find(localTpn);
    if (tpIt != m_tpnMap.end()) {
        ApplyScheduleWqeSegment(tpIt->second);
    }
}

Ptr<UbWqeSegment> UbTransaction::ExecuteRemoteWriteAndBuildAck(uint32_t localTpn,
                                                               Ptr<UbWqeSegment> request)
{
    if (request == nullptr) {
        return nullptr;
    }

    const uint64_t address = DeriveRemoteAddress(request);
    m_memoryStore[std::make_pair(m_nodeId, address)] = request->GetSize();

    Ptr<UbWqeSegment> response = CreateObject<UbWqeSegment>();
    response->SetSrc(m_nodeId);
    response->SetDest(request->GetSrc());
    response->SetSport(request->GetDport());
    response->SetDport(request->GetSport());
    response->SetType(TaOpcode::TA_OPCODE_TRANSACTION_ACK);
    // Keep a non-zero carrier so the existing TP scheduler will serialize one response packet.
    response->SetSize(1);
    response->SetPriority(request->GetPriority());
    response->SetTaskId(request->GetTaskId());
    response->SetWqeSize(request->GetWqeSize());
    response->SetOrderType(request->GetOrderType());
    response->SetJettyNum(request->GetOriginJettyNum());
    response->SetTaMsn(0);
    response->SetTaSsn(request->GetRequestTassn());
    response->SetSegmentKind(UbTransactionSegmentKind::RESPONSE);
    response->SetOriginJettyNum(request->GetOriginJettyNum());
    response->SetRequestTassn(request->GetRequestTassn());
    response->SetRequestOpcode(TaOpcode::TA_OPCODE_WRITE);
    response->SetResponseBytes(0);
    response->SetRemoteAddress(address);
    response->SetNeedsTransactionResponse(false);
    response->SetTpn(localTpn);
    return response;
}

Ptr<UbWqeSegment> UbTransaction::ExecuteRemoteReadAndBuildResponse(uint32_t localTpn,
                                                                   Ptr<UbWqeSegment> request)
{
    if (request == nullptr) {
        return nullptr;
    }

    const uint64_t address = DeriveRemoteAddress(request);
    const auto memoryIt = m_memoryStore.find(std::make_pair(m_nodeId, address));
    const uint32_t responseBytes = request->GetResponseBytes() == 0 ? request->GetSize()
                                                                     : request->GetResponseBytes();
    (void)memoryIt;

    Ptr<UbWqeSegment> response = CreateObject<UbWqeSegment>();
    response->SetSrc(m_nodeId);
    response->SetDest(request->GetSrc());
    response->SetSport(request->GetDport());
    response->SetDport(request->GetSport());
    response->SetType(TaOpcode::TA_OPCODE_READ_RESPONSE);
    response->SetSize(responseBytes);
    response->SetPriority(request->GetPriority());
    response->SetTaskId(request->GetTaskId());
    response->SetWqeSize(request->GetWqeSize());
    response->SetOrderType(request->GetOrderType());
    response->SetJettyNum(request->GetOriginJettyNum());
    response->SetTaMsn(0);
    response->SetTaSsn(request->GetRequestTassn());
    response->SetSegmentKind(UbTransactionSegmentKind::RESPONSE);
    response->SetOriginJettyNum(request->GetOriginJettyNum());
    response->SetRequestTassn(request->GetRequestTassn());
    response->SetRequestOpcode(TaOpcode::TA_OPCODE_READ);
    response->SetResponseBytes(responseBytes);
    response->SetRemoteAddress(address);
    response->SetNeedsTransactionResponse(false);
    response->SetTpn(localTpn);
    return response;
}

void UbTransaction::CompleteLocalRequestFromResponse(Ptr<UbWqeSegment> response)
{
    if (response == nullptr) {
        return;
    }

    const bool isWriteAck =
        response->GetType() == TaOpcode::TA_OPCODE_TRANSACTION_ACK &&
        response->GetRequestOpcode() == TaOpcode::TA_OPCODE_WRITE;
    const bool isReadResponse =
        response->GetType() == TaOpcode::TA_OPCODE_READ_RESPONSE &&
        response->GetRequestOpcode() == TaOpcode::TA_OPCODE_READ;
    if (!isWriteAck && !isReadResponse) {
        return;
    }

    ProcessWqeSegmentComplete(response);
}

uint64_t UbTransaction::DeriveRemoteAddress(const Ptr<UbWqeSegment>& request) const
{
    NS_ASSERT_MSG(request != nullptr, "request must exist when deriving a remote address");
    return request->GetRemoteAddress() +
           static_cast<uint64_t>(request->GetTaSsn()) * UB_WQE_TA_SEGMENT_BYTE;
}

void UbTransaction::TriggerTpTransmit(uint32_t jettyNum)
{
    const std::vector<Ptr<UbTransportChannel>> ubTransportGroupVec = GetJettyRelatedTpVec(jettyNum);
    for (uint32_t i = 0; i < ubTransportGroupVec.size(); i++) {
        ubTransportGroupVec[i]->ApplyNextWqeSegment();
    }
}

bool UbTransaction::IsOrderedByInitiator(uint32_t jettyNum, Ptr<UbWqe> wqe)
{
    if (m_serviceMode.find(jettyNum) == m_serviceMode.end()) {
        return false;
    }
    if (m_serviceMode[jettyNum] != TransactionServiceMode::ROI) { // 不是ROI，直接返回true
        return true;
    }
    bool res = false;
    bool orderedEmpty = m_jettyOrderedWqe[jettyNum].empty();
    switch (wqe->GetOrderType()) {
        case OrderType::ORDER_NO:
        case OrderType::ORDER_RESERVED:
            res = true;
            break;
        case OrderType::ORDER_RELAX:
            NS_ASSERT_MSG(!orderedEmpty, "RO/SO Wqe should in Ordered vector!");
            res = true;
            break;
        case OrderType::ORDER_STRONG:
            NS_ASSERT_MSG(!orderedEmpty, "RO/SO Wqe should in Ordered vector!");
            res = (m_jettyOrderedWqe[jettyNum].front() == wqe->GetWqeId());
            break;
        default:
            NS_ASSERT_MSG(0, "Invalid Transaction Order Type!");
    }
    return res;
}

void UbTransaction::SetTransactionServiceMode(uint32_t jettyNum, TransactionServiceMode mode)
{
    m_serviceMode[jettyNum] = mode;
    // ROI模式下且wqeVector中尚无该jetty的记录，则新建
    if (mode == TransactionServiceMode::ROI && m_jettyOrderedWqe.find(jettyNum) == m_jettyOrderedWqe.end()) {
        m_jettyOrderedWqe[jettyNum] = std::vector<uint32_t>();
    }
}

TransactionServiceMode UbTransaction::GetTransactionServiceMode(uint32_t jettyNum)
{
    if (m_serviceMode.find(jettyNum) != m_serviceMode.end()) {
        return m_serviceMode[jettyNum];
    } else { //默认为ROI
        return TransactionServiceMode::ROI;
    }
}


bool UbTransaction::IsOrderedByTarget(Ptr<UbWqe> wqe)
{
    NS_LOG_DEBUG("IsOrderedByTarget");
    return true;
}

bool UbTransaction::IsReliable(Ptr<UbWqe> wqe)
{
    return true;
}

bool UbTransaction::IsUnreliable(Ptr<UbWqe> wqe)
{
    return false;
}

void UbTransaction::AddWqe(uint32_t jettyNum, Ptr<UbWqe> wqe)
{
    if (m_serviceMode.find(jettyNum) != m_serviceMode.end()) {
        // ROI模式且wqe是RO或SO
        if (m_serviceMode[jettyNum] == TransactionServiceMode::ROI
            && (wqe->GetOrderType() == OrderType::ORDER_RELAX || wqe->GetOrderType() == OrderType::ORDER_STRONG)) {
            m_jettyOrderedWqe[jettyNum].push_back(wqe->GetWqeId());
        }
    } else {
        SetTransactionServiceMode(jettyNum, TransactionServiceMode::ROI);
        AddWqe(jettyNum, wqe);
    }
}

void UbTransaction::WqeFinish(uint32_t jettyNum, Ptr<UbWqe> wqe)
{
    if (m_serviceMode.find(jettyNum) == m_serviceMode.end() || m_serviceMode[jettyNum] != TransactionServiceMode::ROI) {
        return;
    }
    // 从vector中寻找该wqe并删除
    auto it = std::find(m_jettyOrderedWqe[jettyNum].begin(), m_jettyOrderedWqe[jettyNum].end(), wqe->GetWqeId());
    if (it != m_jettyOrderedWqe[jettyNum].end()) {
        m_jettyOrderedWqe[jettyNum].erase(it);
    }
}

void UbTransaction::DoDispose()
{
    NS_LOG_FUNCTION(this);
    m_tpnMap.clear();
    m_jettyOrderedWqe.clear();
    for (auto &it : m_jettyTpGroup) {
        for (auto tp : it.second) {
            tp = nullptr;
        }
    }
    m_jettyTpGroup.clear();
    m_jettyDestNode.clear();
    m_jettyScheduledWqeId.clear();
    m_jettyTpScheduleIndex.clear();
    m_jettyPortScheduledSegmentCount.clear();
    m_jettyTpScheduledSegmentCount.clear();
    for (auto &it : m_tpRelatedJetties) {
        for(auto jetty : it.second) {
            jetty = nullptr;
        }
    }
    m_tpRelatedJetties.clear();
    for (auto &it : m_tpRelatedRemoteRequests) {
        for (auto &remoteMap : it.second) {
            for (auto segment : remoteMap.second) {
                segment = nullptr;
            }
        }
    }
    m_tpRelatedRemoteRequests.clear();
    m_tpRRIndex.clear();
    m_tpSchedulingStatus.clear();
    m_random = nullptr;
    m_serviceMode.clear();
    m_memoryStore.clear();
    for (auto &it : m_jettyOrderedWqe) {
        it.second.clear();
    }
    m_jettyOrderedWqe.clear();
    Object::DoDispose();
}

std::vector<uint32_t> UbTransaction::GetUselessTpns()
{
    std::vector<uint32_t> tpns;
    // 遍历tp，找出所有本地和对端都不再使用的tp
    for (auto it = m_tpnMap.begin(); it != m_tpnMap.end(); it++) {
        uint32_t tpn = it->first;
        if (!IsTpInUse(tpn) && !IsPeerTpInUse(tpn)) {
            tpns.push_back(tpn);
        }
    }
    return tpns;
}

bool UbTransaction::IsTpInUse(uint32_t tpn)
{
    NS_ASSERT_MSG(m_tpnMap.find(tpn) != m_tpnMap.end(), "no such tp.");
    auto it = m_tpRelatedJetties.find(tpn);
    if (it == m_tpRelatedJetties.end()) {
        // 不存在记录表示无jetty使用
        return false;
    }
    // 若存在记录且对应jetty数目为0，表示使用完毕，非0，表示正在使用
    return (it->second.size() != 0);
}

bool UbTransaction::IsPeerTpInUse(uint32_t tpn)
{
    auto localTpIt = m_tpnMap.find(tpn);
    NS_ASSERT_MSG(localTpIt != m_tpnMap.end(), "can't find local tpn");
    auto localTp = localTpIt->second;
    uint32_t dst = localTp->GetDest();
    uint32_t dstTpn = localTp->GetDstTpn();
    auto peerTa = NodeList::GetNode(dst)->GetObject<UbController>()->GetUbTransaction();
    return peerTa->IsTpInUse(dstTpn);
}

} // namespace ns3
