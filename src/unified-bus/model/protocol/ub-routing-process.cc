// SPDX-License-Identifier: GPL-2.0-only
#include <algorithm>
#include <array>
#include <limits>
#include "ns3/ub-controller.h"
#include "ns3/ub-header.h"
#include "ns3/ub-network-address.h"
#include "ns3/ub-port.h"
#include "ns3/ub-queue-manager.h"
#include "ns3/ub-routing-process.h"
#include "ns3/udp-header.h"
#include "ns3/ipv4-header.h"
using namespace utils;

namespace ns3 {
NS_OBJECT_ENSURE_REGISTERED(UbRoutingProcess);
NS_LOG_COMPONENT_DEFINE("UbRoutingProcess");

namespace
{
constexpr uint32_t kPrimaryRangeRoutePort = std::numeric_limits<uint32_t>::max();
}

/*-----------------------------------------UbRoutingProcess----------------------------------------------*/
TypeId UbRoutingProcess::GetTypeId(void)
{
    static TypeId tid = TypeId("ns3::UbRoutingProcess")
        .SetParent<Object>()
        .SetGroupName("UnifiedBus")
        .AddConstructor<UbRoutingProcess>()
        .AddAttribute("MultipathSelector",
                    "Selector used to choose one path from the routing candidate set.",
                    EnumValue(MultipathSelector::HASH64),
                    MakeEnumAccessor<MultipathSelector>(&UbRoutingProcess::m_multipathSelector),
                    MakeEnumChecker(MultipathSelector::HASH64, "HASH64",
                                    MultipathSelector::CRC32, "CRC32",
                                    MultipathSelector::TOEPLITZ, "TOEPLITZ",
                                    MultipathSelector::ROUND_ROBIN, "ROUND_ROBIN",
                                    MultipathSelector::ADAPTIVE, "ADAPTIVE",
                                    MultipathSelector::INGRESS_PORT_STRIPE,
                                    "INGRESS_PORT_STRIPE"));
    return tid;
}

UbRoutingProcess::UbRoutingProcess()
{
}

void
UbRoutingProcess::ValidateRoutingType(RoutingType routingType, const std::string& owner) const
{
    if (MultipathSelectorIsValidForRoutingType(m_multipathSelector, routingType))
    {
        return;
    }

    const RoutingType compatibleRoutingType =
        MakeRoutingType(m_multipathSelector != MultipathSelector::INGRESS_PORT_STRIPE,
                        RoutingTypeUsesShortestPaths(routingType));
    NS_ABORT_MSG("Invalid routing configuration for "
                 << owner << ": RoutingType \"" << RoutingTypeToString(routingType)
                 << "\" cannot be combined with MultipathSelector \""
                 << MultipathSelectorToString(m_multipathSelector)
                 << "\". Use RoutingType \"" << RoutingTypeToString(compatibleRoutingType)
                 << "\" or MultipathSelector \"HASH64\".");
}

std::shared_ptr<std::vector<uint16_t> >
UbRoutingProcess::GetOrCreatePortSet(const std::vector<uint16_t>& ports)
{
    std::vector<uint16_t> normalized = normalizePorts(ports);
    auto it = m_portSetPool.find(normalized);
    if (it != m_portSetPool.end())
    {
        return it->second;
    }

    auto sharedPorts = std::make_shared<std::vector<uint16_t>>(normalized);
    m_portSetPool[normalized] = sharedPorts;
    return sharedPorts;
}

void UbRoutingProcess::AddShortestRoute(const uint32_t destIP, const std::vector<uint16_t>& outPorts)
{
    // 标准化端口集合（排序去重）
    std::vector<uint16_t> target;
    auto itRt = m_rtShortest.find(destIP);
    if (itRt != m_rtShortest.end()) {
        target.insert(target.end(), (*(itRt->second)).begin(), (*(itRt->second)).end());
    }
    target.insert(target.end(), outPorts.begin(), outPorts.end());
    m_rtShortest[destIP] = GetOrCreatePortSet(target);
}

void UbRoutingProcess::AddOtherRoute(const uint32_t destIP, const std::vector<uint16_t>& outPorts)
{
    // 标准化端口集合（排序去重）
    std::vector<uint16_t> target;
    auto itRt = m_rtOther.find(destIP);
    if (itRt != m_rtOther.end()) {
        target.insert(target.end(), (*(itRt->second)).begin(), (*(itRt->second)).end());
    }
    target.insert(target.end(), outPorts.begin(), outPorts.end());
    m_rtOther[destIP] = GetOrCreatePortSet(target);
}

void
UbRoutingProcess::AddRouteRange(RouteRangeByPortMap& routeRangesByPort,
                                uint32_t startNodeId,
                                uint32_t endNodeId,
                                uint32_t dstPortId,
                                const std::vector<uint16_t>& outPorts)
{
    AddRouteRangeToMap(routeRangesByPort[dstPortId], startNodeId, endNodeId, outPorts);
}

void
UbRoutingProcess::AddRouteRangeToMap(RouteRangeMap& routeRanges,
                                     uint32_t startNodeId,
                                     uint32_t endNodeId,
                                     const std::vector<uint16_t>& outPorts)
{
    NS_ASSERT_MSG(startNodeId <= endNodeId, "route range start must not exceed end");

    auto valueAt = [&routeRanges](uint32_t nodeId) -> std::shared_ptr<std::vector<uint16_t> > {
        auto it = routeRanges.upper_bound(nodeId);
        if (it == routeRanges.begin())
        {
            return nullptr;
        }
        --it;
        return it->second;
    };

    if (routeRanges.find(startNodeId) == routeRanges.end())
    {
        routeRanges[startNodeId] = valueAt(startNodeId);
    }
    if (endNodeId != std::numeric_limits<uint32_t>::max())
    {
        const uint32_t afterEnd = endNodeId + 1;
        if (routeRanges.find(afterEnd) == routeRanges.end())
        {
            routeRanges[afterEnd] = valueAt(afterEnd);
        }
    }

    for (auto it = routeRanges.lower_bound(startNodeId);
         it != routeRanges.end() && it->first <= endNodeId;
         ++it)
    {
        std::vector<uint16_t> target;
        if (it->second != nullptr)
        {
            target.insert(target.end(), it->second->begin(), it->second->end());
        }
        target.insert(target.end(), outPorts.begin(), outPorts.end());
        it->second = GetOrCreatePortSet(target);
    }
}

void
UbRoutingProcess::AddShortestRouteRange(uint32_t startNodeId,
                                        uint32_t endNodeId,
                                        const std::vector<uint16_t>& outPorts)
{
    AddShortestRouteRange(startNodeId, endNodeId, 0, outPorts);
}

void
UbRoutingProcess::AddOtherRouteRange(uint32_t startNodeId,
                                     uint32_t endNodeId,
                                     const std::vector<uint16_t>& outPorts)
{
    AddOtherRouteRange(startNodeId, endNodeId, 0, outPorts);
}

void
UbRoutingProcess::AddShortestRouteRange(uint32_t startNodeId,
                                        uint32_t endNodeId,
                                        uint32_t dstPortId,
                                        const std::vector<uint16_t>& outPorts)
{
    AddRouteRange(m_rtShortestRanges,
                  startNodeId,
                  endNodeId,
                  kPrimaryRangeRoutePort,
                  outPorts);
    AddRouteRange(m_rtShortestRanges, startNodeId, endNodeId, dstPortId, outPorts);
}

void
UbRoutingProcess::AddOtherRouteRange(uint32_t startNodeId,
                                     uint32_t endNodeId,
                                     uint32_t dstPortId,
                                     const std::vector<uint16_t>& outPorts)
{
    AddRouteRange(m_rtOtherRanges,
                  startNodeId,
                  endNodeId,
                  kPrimaryRangeRoutePort,
                  outPorts);
    AddRouteRange(m_rtOtherRanges, startNodeId, endNodeId, dstPortId, outPorts);
}

bool
UbRoutingProcess::GetRangeOutPortsFromMap(const RouteRangeMap& routeRanges,
                                          uint32_t nodeId,
                                          std::vector<uint16_t>& outPorts)
{
    if (routeRanges.empty())
    {
        return false;
    }

    auto it = routeRanges.upper_bound(nodeId);
    if (it == routeRanges.begin())
    {
        return false;
    }
    --it;
    if (it->second == nullptr)
    {
        return false;
    }
    outPorts.insert(outPorts.end(), it->second->begin(), it->second->end());
    return true;
}

void
UbRoutingProcess::GetRangeOutPorts(const RouteRangeByPortMap& routeRangesByPort,
                                   const uint32_t destIP,
                                   std::vector<uint16_t>& outPorts)
{
    if (routeRangesByPort.empty())
    {
        return;
    }

    const Ipv4Address ip(destIP);
    const uint32_t nodeId = utils::IpToNodeId(ip);
    const uint32_t lastByte = destIP & 0x000000ff;
    const uint32_t portId = lastByte == 0 ? kPrimaryRangeRoutePort : lastByte - 1;
    auto portIt = routeRangesByPort.find(portId);
    if (portIt != routeRangesByPort.end())
    {
        GetRangeOutPortsFromMap(portIt->second, nodeId, outPorts);
    }
}

void UbRoutingProcess::GetShortestOutPorts(const uint32_t destIP, std::vector<uint16_t>& outPorts)
{
    outPorts.clear();
    auto it = m_rtShortest.find(destIP);
    if (it != m_rtShortest.end()) {
        outPorts.insert(outPorts.end(), (*(it->second)).begin(), (*(it->second)).end());
        return;
    }
    GetRangeOutPorts(m_rtShortestRanges, destIP, outPorts);
}

void UbRoutingProcess::GetOtherOutPorts(const uint32_t destIP, std::vector<uint16_t>& outPorts)
{
    outPorts.clear();
    auto it = m_rtOther.find(destIP);
    if (it != m_rtOther.end()) {
        outPorts.insert(outPorts.end(), (*(it->second)).begin(), (*(it->second)).end());
        return;
    }
    GetRangeOutPorts(m_rtOtherRanges, destIP, outPorts);
}

void UbRoutingProcess::GetShortestCandidates(uint32_t &dip, uint16_t inPortId, std::vector<uint16_t>& outPorts)
{
    // 1. 首先基于目的节点的port地址进行选择
    GetShortestOutPorts(dip, outPorts);
    if (outPorts.empty()) {
        // 2. 如果找不到，掩盖port地址，使用主机的primary地址进行寻址
        Ipv4Mask mask("255.255.255.0");
        uint32_t maskedDip = Ipv4Address(dip).CombineMask(mask).Get();
        if (maskedDip != dip) {
            GetShortestOutPorts(maskedDip, outPorts);
            dip = maskedDip;
        }
    }

    // 3. 过滤掉入端口
    if (inPortId != UINT16_MAX) {
        auto it = std::remove_if(outPorts.begin(), outPorts.end(), 
                                  [inPortId](uint16_t port) { return port == inPortId; });
        outPorts.erase(it, outPorts.end());
    }
}

void UbRoutingProcess::GetNonShortestCandidates(uint32_t &dip, uint16_t inPortId, std::vector<uint16_t>& outPorts)
{
    // 1. 首先基于目的节点的port地址进行选择
    GetOtherOutPorts(dip, outPorts);
    if (outPorts.empty()) {
        // 2. 如果找不到，掩盖port地址，使用主机的primary地址进行寻址
        Ipv4Mask mask("255.255.255.0");
        uint32_t maskedDip = Ipv4Address(dip).CombineMask(mask).Get();
        if (maskedDip != dip) {
            GetOtherOutPorts(maskedDip, outPorts);
            dip = maskedDip;
        }
    }

    // 3. 过滤掉入端口
    if (inPortId != UINT16_MAX) {
        auto it = std::remove_if(outPorts.begin(), outPorts.end(), 
                                  [inPortId](uint16_t port) { return port == inPortId; });
        outPorts.erase(it, outPorts.end());
    }
}

const std::vector<uint16_t> UbRoutingProcess::GetAllOutPorts(const uint32_t destIP)
{
    std::vector<uint16_t> res;
    auto it = m_rtOther.find(destIP);
    if (it != m_rtOther.end()) {
        res.insert(res.end(), (*(it->second)).begin(), (*(it->second)).end());
    } else {
        GetRangeOutPorts(m_rtOtherRanges, destIP, res);
    }
    it = m_rtShortest.find(destIP);
    if (it != m_rtShortest.end()) {
        res.insert(res.end(), (*(it->second)).begin(), (*(it->second)).end());
    } else {
        GetRangeOutPorts(m_rtShortestRanges, destIP, res);
    }
    return res;
}


// 删除路由条目
bool UbRoutingProcess::RemoveShortestRoute(const uint32_t destIP)
{
    return m_rtShortest.erase(destIP) > 0;
}

// 删除路由条目
bool UbRoutingProcess::RemoveOtherRoute(const uint32_t destIP)
{
    return m_rtOther.erase(destIP) > 0;
}

int UbRoutingProcess::SelectAdaptiveOutPort(RoutingKey &rtKey, const std::vector<uint16_t>& shortestPorts,
                                             const std::vector<uint16_t>& nonShortestPorts, bool &selectedShortestPath)
{
    auto node = NodeList::GetNode(m_nodeId);
    auto ubSwitch = node->GetObject<UbSwitch>();
    auto queueManager = ubSwitch->GetQueueManager();
    uint8_t priority = rtKey.priority;

    auto calcLoadScore = [&](uint16_t outPort) -> uint64_t {
        if (queueManager == nullptr) {
            return 0;
        }
        // 使用OutPort视图统计VOQ占用
        uint64_t voqLoad = queueManager->GetOutPortBufferUsed(outPort, static_cast<uint32_t>(priority));
        
        // 加上EgressQueue的字节占用
        Ptr<UbPort> port = DynamicCast<UbPort>(node->GetDevice(outPort));
        uint64_t egressLoad = port->GetUbQueue()->GetCurrentBytes();
        
        // 总负载 = VOQ + EgressQueue
        return voqLoad + egressLoad;
    };

    // 构造总候选列表：先 shortest，后 nonShortest
    std::vector<uint16_t> candidatePorts;
    candidatePorts.insert(candidatePorts.end(), shortestPorts.begin(), shortestPorts.end());
    candidatePorts.insert(candidatePorts.end(), nonShortestPorts.begin(), nonShortestPorts.end());

    if (candidatePorts.empty()) {
        return -1;
    }

    uint64_t bestScore = std::numeric_limits<uint64_t>::max();
    std::vector<uint16_t> bestPorts;
    size_t bestIndex = 0;
    for (size_t i = 0; i < candidatePorts.size(); ++i) {
        uint16_t port = candidatePorts[i];
        uint64_t score = calcLoadScore(port);
        if (score < bestScore) {
            bestScore = score;
            bestPorts.clear();
            bestPorts.push_back(port);
            bestIndex = i;
        } else if (score == bestScore) {
            bestPorts.push_back(port);
        }
    }

    if (bestPorts.empty()) {
        return -1;
    }

    // 通过索引判断是否选中最短路径
    selectedShortestPath = (bestIndex < shortestPorts.size());
    uint16_t selectedPort = bestPorts.front();
    return selectedPort;
}

std::array<uint8_t, 17>
UbRoutingProcess::BuildHashBytes(const RoutingKey& rtKey) const
{
    const uint32_t salt = utils::NodeIdToIp(m_nodeId).Get();
    return {
        static_cast<uint8_t>((rtKey.sip >> 24) & 0xff),
        static_cast<uint8_t>((rtKey.sip >> 16) & 0xff),
        static_cast<uint8_t>((rtKey.sip >> 8) & 0xff),
        static_cast<uint8_t>(rtKey.sip & 0xff),
        static_cast<uint8_t>((rtKey.dip >> 24) & 0xff),
        static_cast<uint8_t>((rtKey.dip >> 16) & 0xff),
        static_cast<uint8_t>((rtKey.dip >> 8) & 0xff),
        static_cast<uint8_t>(rtKey.dip & 0xff),
        static_cast<uint8_t>((rtKey.sport >> 8) & 0xff),
        static_cast<uint8_t>(rtKey.sport & 0xff),
        static_cast<uint8_t>((rtKey.dport >> 8) & 0xff),
        static_cast<uint8_t>(rtKey.dport & 0xff),
        rtKey.priority,
        static_cast<uint8_t>((salt >> 24) & 0xff),
        static_cast<uint8_t>((salt >> 16) & 0xff),
        static_cast<uint8_t>((salt >> 8) & 0xff),
        static_cast<uint8_t>(salt & 0xff),
    };
}

uint32_t
UbRoutingProcess::CalcCrc32(const std::array<uint8_t, 17>& bytes) const
{
    uint32_t crc = 0xffffffffU;
    for (uint8_t byte : bytes)
    {
        crc ^= byte;
        for (uint8_t bit = 0; bit < 8; ++bit)
        {
            crc = (crc >> 1) ^ ((crc & 1U) ? 0xedb88320U : 0U);
        }
    }
    return ~crc;
}

uint32_t
UbRoutingProcess::CalcToeplitzHash(const std::array<uint8_t, 17>& bytes) const
{
    static constexpr std::array<uint8_t, 40> key = {
        0x6d, 0x5a, 0x56, 0xda, 0x25, 0x5b, 0x0e, 0xc2,
        0x41, 0x67, 0x25, 0x3d, 0x43, 0xa3, 0x8f, 0xb0,
        0xd0, 0xca, 0x2b, 0xcb, 0xae, 0x7b, 0x30, 0xb4,
        0x77, 0xcb, 0x2d, 0xa3, 0x80, 0x30, 0xf2, 0x0c,
        0x6a, 0x42, 0xb7, 0x3b, 0xbe, 0xac, 0x01, 0xfa,
    };

    auto keyWindow = [](uint32_t bitOffset) {
        uint32_t value = 0;
        for (uint32_t bit = 0; bit < 32; ++bit)
        {
            const uint32_t position = bitOffset + bit;
            value = (value << 1) |
                    ((key[position / 8] >> (7 - (position % 8))) & 1U);
        }
        return value;
    };

    uint32_t hash = 0;
    uint32_t bitOffset = 0;
    for (uint8_t byte : bytes)
    {
        for (uint8_t bit = 0; bit < 8; ++bit, ++bitOffset)
        {
            if (((byte >> (7 - bit)) & 1U) != 0)
            {
                hash ^= keyWindow(bitOffset);
            }
        }
    }
    return hash;
}

int UbRoutingProcess::SelectOutPort(RoutingKey &rtKey, const std::vector<uint16_t>& shortestPorts, 
                                     const std::vector<uint16_t>& nonShortestPorts,
                                     bool &selectedShortestPath, uint16_t inPort)
{
    ValidateRoutingType(rtKey.routingType, "packet forwarding");
    size_t totalSize = shortestPorts.size() + nonShortestPorts.size();

    if (totalSize == 0) {
        return -1;
    }

    uint64_t hash = 0;
    size_t idx = 0;
    switch (m_multipathSelector)
    {
    case MultipathSelector::HASH64:
    {
        const auto bytes = BuildHashBytes(rtKey);
        hash = Hash64(reinterpret_cast<const char*>(bytes.data()), bytes.size());
        break;
    }
    case MultipathSelector::CRC32:
    {
        const auto bytes = BuildHashBytes(rtKey);
        hash = CalcCrc32(bytes);
        break;
    }
    case MultipathSelector::TOEPLITZ:
    {
        const auto bytes = BuildHashBytes(rtKey);
        hash = CalcToeplitzHash(bytes);
        break;
    }
    case MultipathSelector::ROUND_ROBIN:
    {
        std::vector<uint16_t> candidatePorts;
        candidatePorts.insert(candidatePorts.end(), shortestPorts.begin(), shortestPorts.end());
        candidatePorts.insert(candidatePorts.end(), nonShortestPorts.begin(), nonShortestPorts.end());
        uint64_t& nextIndex = m_rrNextIndexByCandidates[candidatePorts];
        idx = nextIndex % totalSize;
        ++nextIndex;
        if (idx < shortestPorts.size())
        {
            selectedShortestPath = true;
            return shortestPorts[idx];
        }
        selectedShortestPath = false;
        return nonShortestPorts[idx - shortestPorts.size()];
    }
    case MultipathSelector::INGRESS_PORT_STRIPE:
        if (inPort == UINT16_MAX)
        {
            const auto bytes = BuildHashBytes(rtKey);
            hash = Hash64(reinterpret_cast<const char*>(bytes.data()), bytes.size());
            break;
        }
        idx = inPort % totalSize;
        if (idx < shortestPorts.size())
        {
            selectedShortestPath = true;
            return shortestPorts[idx];
        }
        selectedShortestPath = false;
        return nonShortestPorts[idx - shortestPorts.size()];
    case MultipathSelector::ADAPTIVE:
        return SelectAdaptiveOutPort(rtKey,
                                     shortestPorts,
                                     nonShortestPorts,
                                     selectedShortestPath);
    default:
        return -1;
    }
    
    idx = hash % totalSize;
    
    // 通过索引判断是否选中最短路径，并直接返回对应集合中的端口
    if (idx < shortestPorts.size()) {
        selectedShortestPath = true;
        return shortestPorts[idx];
    } else {
        selectedShortestPath = false;
        return nonShortestPorts[idx - shortestPorts.size()];
    }
}

int UbRoutingProcess::GetOutPort(RoutingKey &rtKey, bool &selectedShortestPath, uint16_t inPort)
{
    uint32_t sip = rtKey.sip;
    uint32_t dip = rtKey.dip;
    uint16_t sport = rtKey.sport;
    uint16_t dport = rtKey.dport;
    uint8_t priority = rtKey.priority;
    const RoutingType routingType = rtKey.routingType;
    NS_LOG_DEBUG("[UbRoutingProcess GetOutPort]: sip: " << Ipv4Address(sip)
                << " dip: " << Ipv4Address(dip)
                << " sport: " << sport
                << " dport: " << dport
                << " priority: " << (uint16_t)priority
                << " routingType: " << static_cast<uint32_t>(routingType));
    
    uint32_t tempDip = dip;
    
    // 分别获取最短路径和非最短路径候选端口
    std::vector<uint16_t> shortestPorts;
    std::vector<uint16_t> nonShortestPorts;
    GetShortestCandidates(tempDip, inPort, shortestPorts);
    if (!RoutingTypeUsesShortestPaths(routingType)) {
        // 只有在不限制最短路径时，才获取非最短路径候选端口
        GetNonShortestCandidates(tempDip, inPort, nonShortestPorts);
    }
    
    // 检查是否有可用端口
    if (shortestPorts.empty() && nonShortestPorts.empty()) {
        NS_LOG_ERROR("No candidate ports found for dip: " << Ipv4Address(dip));
        return -1;
    }

    // 基于路由算法选择出端口，同时获得 selectedShortestPath 标记
    int outPortId = -1;
    outPortId = SelectOutPort(rtKey,
                              shortestPorts,
                              nonShortestPorts,
                              selectedShortestPath,
                              inPort);

    // 若找不到出端口，报ASSERT
    NS_ASSERT_MSG(outPortId != -1, "No available output port found");
    
    return outPortId;
}
} // namespace ns3
