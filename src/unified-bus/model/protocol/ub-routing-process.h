// SPDX-License-Identifier: GPL-2.0-only
#ifndef UB_ROUTING_PROCESS_H
#define UB_ROUTING_PROCESS_H

#include "ns3/node.h"
#include <map>
#include <mutex>
#include <set>
#include <string>
#include <tuple>
#include <unordered_map>
namespace ns3 {

class UbQueueManager;
class UbController;
class UbPacketQueue;

/**
 * @brief 查路由需要的相关参数
 */
struct RoutingKey {
    uint32_t sip;        // 源IP，或者SCNA
    uint32_t dip;        // 目的IP，或者DCNA
    uint16_t sport;      // UDP源端口，或者LB字段
    uint16_t dport;      // 目的端口，一般UDP为固定值4792；LDST CFG=9 一般拿不到这个值，写0
    uint8_t priority;    // 优先级
    bool useShortestPath;
    bool usePacketSpray;
};

/**
 * @brief 路由模块
 */
class UbRoutingProcess : public Object {
public:
    UbRoutingProcess();
    ~UbRoutingProcess() {}
    static TypeId GetTypeId(void);
    static bool GetDefaultBwWeightedPacketSpray();
    void SetNodeId(uint32_t nodeId)
    {
        m_nodeId = nodeId;
        m_hasNodeId = true;
    }

    // 添加路由条目
    void AddShortestRoute(const uint32_t destIP, const std::vector<uint16_t>& outPorts);
    void AddOtherRoute(const uint32_t destIP, const std::vector<uint16_t>& outPorts);
    void AddShortestRouteRange(uint32_t startNodeId,
                               uint32_t endNodeId,
                               const std::vector<uint16_t>& outPorts);
    void AddOtherRouteRange(uint32_t startNodeId,
                            uint32_t endNodeId,
                            const std::vector<uint16_t>& outPorts);
    void AddShortestRouteRange(uint32_t startNodeId,
                               uint32_t endNodeId,
                               uint32_t dstPortId,
                               const std::vector<uint16_t>& outPorts);
    void AddOtherRouteRange(uint32_t startNodeId,
                            uint32_t endNodeId,
                            uint32_t dstPortId,
                            const std::vector<uint16_t>& outPorts);
    
    void GetShortestOutPorts(const uint32_t destIP, std::vector<uint16_t>& outPorts) const;
    void GetOtherOutPorts(const uint32_t destIP, std::vector<uint16_t>& outPorts) const;
    const std::vector<uint16_t> GetAllOutPorts(const uint32_t destIP);
    
    // 获取最短路径候选端口和非最短路径候选端口
    void GetShortestCandidates(uint32_t &dip, uint16_t inPortId, std::vector<uint16_t>& outPorts) const;
    void GetNonShortestCandidates(uint32_t &dip, uint16_t inPortId, std::vector<uint16_t>& outPorts) const;
    int GetOutPort(RoutingKey &rtKey, bool &selectedShortestPath, uint16_t inPort = UINT16_MAX);
    int SelectOutPort(RoutingKey &rtKey, const std::vector<uint16_t>& shortestPorts, 
                      const std::vector<uint16_t>& nonShortestPorts, bool &selectedShortestPath,
                      uint16_t inPort = UINT16_MAX);
    uint64_t GetGlobalOracleOutPortWeight(uint16_t outPort,
                                          uint32_t destIP,
                                          uint16_t inPortId,
                                          bool useShortestPath) const;
    // 自适应路由策略
    int SelectAdaptiveOutPort(RoutingKey &rtKey, const std::vector<uint16_t>& shortestPorts,
                              const std::vector<uint16_t>& nonShortestPorts, bool &selectedShortestPath);
    // 删除路由条目
    bool RemoveShortestRoute(const uint32_t destIP);
    bool RemoveOtherRoute(const uint32_t destIP);
private:
    using RouteRangeMap = std::map<uint32_t, std::shared_ptr<std::vector<uint16_t> > >;
    using RouteRangeByPortMap = std::map<uint32_t, RouteRangeMap>;

    struct VectorHash {
        size_t operator()(const std::vector<uint16_t>& v) const
        {
            std::string hashKey;
            for (int i : v) {
                hashKey += std::to_string(i);
            }
            return Hash64(hashKey);
        }
    };

    // 操作类型枚举
    enum class UbRoutingAlgorithm : uint8_t {
        HASH = 0,   // Hash-based routing
        ADAPTIVE = 1   // Adaptive routing
    };

    uint32_t m_nodeId = 0;
    bool m_hasNodeId = false;
    UbRoutingAlgorithm m_routingAlgorithm = UbRoutingAlgorithm::HASH;
    bool m_bwWeightedPacketSpray = false;
    std::string m_bwWeightedPacketSprayScope = "all";
    uint64_t CalcHash(uint32_t sip, uint32_t dip, uint16_t sport, uint16_t dport, uint8_t priority, uint32_t salt);
    uint64_t GetLocalPortWeight(uint16_t outPort) const;
    uint64_t GetPacketSprayPortWeight(uint16_t outPort,
                                      uint32_t destIP,
                                      uint16_t inPortId,
                                      bool useShortestPath) const;
    uint64_t GetPacketSprayWeightGcd(const std::vector<uint16_t>& shortestPorts,
                                     const std::vector<uint16_t>& nonShortestPorts,
                                     uint32_t destIP,
                                     uint16_t inPortId,
                                     bool useShortestPath) const;
    uint64_t GetPacketSprayTotalNormalizedWeight(const std::vector<uint16_t>& shortestPorts,
                                                 const std::vector<uint16_t>& nonShortestPorts,
                                                 uint32_t destIP,
                                                 uint16_t inPortId,
                                                 bool useShortestPath) const;
    uint64_t GetPacketSprayStride(uint64_t flowBase, uint64_t cycleLength) const;
    void FilterUnreachablePacketSprayPorts(std::vector<uint16_t>& shortestPorts,
                                           std::vector<uint16_t>& nonShortestPorts,
                                           uint32_t destIP,
                                           uint16_t inPortId,
                                           bool useShortestPath) const;
    bool HasParallelLinksToPeer(uint32_t peerNodeId) const;
    bool BwWeightedPacketSprayScopeMatchesPort(uint16_t outPort) const;
    bool BwWeightedPacketSprayScopeMatches(const std::vector<uint16_t>& shortestPorts,
                                           const std::vector<uint16_t>& nonShortestPorts) const;
    int SelectWeightedPacketSprayOutPort(uint64_t hash64,
                                         const std::vector<uint16_t>& shortestPorts,
                                         const std::vector<uint16_t>& nonShortestPorts,
                                         uint32_t destIP,
                                         uint16_t inPortId,
                                         bool useShortestPath,
                                         bool& selectedShortestPath) const;
    uint64_t GetGlobalOracleTotalCapacity(uint32_t destIP,
                                          uint16_t inPortId,
                                          bool useShortestPath,
                                          std::set<std::tuple<uint32_t, uint32_t, uint16_t, bool>>& visiting) const;
    uint64_t GetGlobalOracleOutPortWeight(uint16_t outPort,
                                          uint32_t destIP,
                                          uint16_t inPortId,
                                          bool useShortestPath,
                                          std::set<std::tuple<uint32_t, uint32_t, uint16_t, bool>>& visiting) const;
    std::shared_ptr<std::vector<uint16_t> > GetOrCreatePortSet(const std::vector<uint16_t>& ports);
    void AddRouteRange(RouteRangeByPortMap& routeRangesByPort,
                       uint32_t startNodeId,
                       uint32_t endNodeId,
                       uint32_t dstPortId,
                       const std::vector<uint16_t>& outPorts);
    void AddRouteRangeToMap(RouteRangeMap& routeRanges,
                       uint32_t startNodeId,
                       uint32_t endNodeId,
                       const std::vector<uint16_t>& outPorts);
    bool GetRangeOutPortsFromMap(const RouteRangeMap& routeRanges,
                                 uint32_t nodeId,
                                 std::vector<uint16_t>& outPorts) const;
    void GetRangeOutPorts(const RouteRangeByPortMap& routeRangesByPort,
                          const uint32_t destIP,
                          std::vector<uint16_t>& outPorts) const;

    // 全局端口集合池：存储所有唯一的端口集合
    std::unordered_map<std::vector<uint16_t>, std::shared_ptr<std::vector<uint16_t> >, VectorHash> m_portSetPool;
    
    // 路由表：目的IP -> 共享的端口集合指针
    std::unordered_map<uint32_t, std::shared_ptr<std::vector<uint16_t> > > m_rtShortest;
    std::unordered_map<uint32_t, std::shared_ptr<std::vector<uint16_t> > > m_rtOther;
    RouteRangeByPortMap m_rtShortestRanges;
    RouteRangeByPortMap m_rtOtherRanges;
    mutable std::map<std::tuple<uint32_t, uint32_t, uint16_t, bool>,
                     std::map<uint16_t, uint64_t>> m_globalOracleCache;
    mutable std::map<std::pair<uint32_t, uint32_t>, bool> m_parallelLinkCache;
    mutable std::mutex m_cacheMutex;
    
    // 辅助函数：标准化端口集合（排序去重）
    std::vector<uint16_t> normalizePorts(const std::vector<uint16_t>& ports)
    {
        std::set<uint16_t> sorted(ports.begin(), ports.end());
        return std::vector<uint16_t>(sorted.begin(), sorted.end());
    }
};

} // namespace ns3

#endif /* UB_RT_TABLE_H */
