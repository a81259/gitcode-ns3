// SPDX-License-Identifier: GPL-2.0-only
#include "ns3/ub-retrans.h"

namespace ns3 {

UbRetransController::UbRetransController(UbTransportChannel& transport)
    : m_transport(transport)
{
}

} // namespace ns3
