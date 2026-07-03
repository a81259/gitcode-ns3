#!/usr/bin/env python3
"""Regression checks for bandwidth-weighted packet-spray configuration."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return (ROOT / path).read_text()


def test_bw_weighted_switch_controls_routing_and_host_scheduling():
    routing_cc = read("src/unified-bus/model/protocol/ub-routing-process.cc")
    routing_h = read("src/unified-bus/model/protocol/ub-routing-process.h")
    transaction_cc = read("src/unified-bus/model/protocol/ub-transaction.cc")
    tp_manager_cc = read("src/unified-bus/model/ub-tp-connection-manager.cc")

    combined = routing_cc + routing_h + transaction_cc + tp_manager_cc
    assert "UseBandwidthWeightedPacketSpray" not in combined
    assert "UseBandwidthWeightedTpScheduling" not in combined
    assert "WeightedPacketSprayScope" not in combined
    assert "POD_LOCAL" not in combined

    assert 'AddAttribute("BwWeightedPacketSpray"' in routing_cc
    assert "bool m_bwWeightedPacketSpray" in routing_h
    assert "GetDefaultBwWeightedPacketSpray" in routing_h
    assert "GetDefaultBwWeightedPacketSpray" in transaction_cc
    assert "GetGlobalOracleOutPortWeight" in routing_h
    assert "GetGlobalOracleOutPortWeight" in tp_manager_cc
    assert "HasNonUniformSchedulingWeights" in transaction_cc

if __name__ == "__main__":
    test_bw_weighted_switch_controls_routing_and_host_scheduling()
