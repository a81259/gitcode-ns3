// SPDX-License-Identifier: GPL-2.0-only
#ifndef UB_RETRANS_H
#define UB_RETRANS_H

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

private:
    UbTransportChannel& m_transport;
};

} // namespace ns3

#endif // UB_RETRANS_H
