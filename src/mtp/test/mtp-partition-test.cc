/*
 * SPDX-License-Identifier: GPL-2.0-only
 */

#include "ns3/boolean.h"
#include "ns3/config.h"
#include "ns3/global-value.h"
#include "ns3/mac48-address.h"
#include "ns3/mtp-interface.h"
#include "ns3/node-container.h"
#include "ns3/simple-channel.h"
#include "ns3/simple-net-device.h"
#include "ns3/simulator.h"
#include "ns3/string.h"
#include "ns3/test.h"
#include "ns3/nstime.h"
#include "ns3/uinteger.h"

using namespace ns3;

namespace
{

void
Noop()
{
}

void
InstallZeroDelayPointToPointLink(Ptr<Node> left, Ptr<Node> right)
{
    Ptr<SimpleChannel> channel = CreateObject<SimpleChannel>();
    channel->SetAttribute("Delay", TimeValue(NanoSeconds(0)));

    for (Ptr<Node> node : {left, right})
    {
        Ptr<SimpleNetDevice> device = CreateObject<SimpleNetDevice>();
        device->SetAttribute("PointToPointMode", BooleanValue(true));
        device->SetAddress(Mac48Address::Allocate());
        node->AddDevice(device);
        device->SetChannel(channel);
        channel->Add(device);
    }
}

class MtpZeroDelayAutoPartitionTest : public TestCase
{
  public:
    MtpZeroDelayAutoPartitionTest()
        : TestCase("MTP auto partition keeps zero-delay connected links in one LP")
    {
    }

  private:
    void DoRun() override
    {
        Config::SetDefault("ns3::MultithreadedSimulatorImpl::MaxThreads", UintegerValue(4));
        Config::SetDefault("ns3::MultithreadedSimulatorImpl::MinLookahead",
                           TimeValue(TimeStep(0)));
        MtpInterface::Enable(4);

        NodeContainer nodes;
        nodes.Create(4);

        InstallZeroDelayPointToPointLink(nodes.Get(0), nodes.Get(1));
        InstallZeroDelayPointToPointLink(nodes.Get(1), nodes.Get(2));
        InstallZeroDelayPointToPointLink(nodes.Get(2), nodes.Get(3));

        Simulator::Schedule(NanoSeconds(1), &Noop);
        Simulator::Run();

        const uint32_t firstSystemId = nodes.Get(0)->GetSystemId();
        for (uint32_t i = 1; i < nodes.GetN(); ++i)
        {
            NS_TEST_ASSERT_MSG_EQ(nodes.Get(i)->GetSystemId(),
                                  firstSystemId,
                                  "zero-delay connected nodes should stay in the same auto "
                                  "partition");
        }
        NS_TEST_ASSERT_MSG_EQ(MtpInterface::GetSize(),
                              2u,
                              "one worker LP plus public LP should be created");

        Simulator::Destroy();
        Config::SetGlobal("SimulatorImplementationType", StringValue("ns3::DefaultSimulatorImpl"));
    }
};

class MtpPartitionTestSuite : public TestSuite
{
  public:
    MtpPartitionTestSuite()
        : TestSuite("mtp-partition", Type::UNIT)
    {
        AddTestCase(new MtpZeroDelayAutoPartitionTest(), TestCase::Duration::QUICK);
    }
};

static MtpPartitionTestSuite g_mtpPartitionTestSuite;

} // namespace
