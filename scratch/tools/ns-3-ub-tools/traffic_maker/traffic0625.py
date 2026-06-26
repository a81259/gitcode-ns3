import csv
import math
from pathlib import Path
from typing import List, Tuple

from algorithms.all_reduce.ring import build_ar_ring_schedule
from algorithms.all_reduce.nhr import build_nhr_schedule
from algorithms.all_reduce.recursive_hd import build_ar_rhd_schedule
from algorithms.schedule import Schedule

# (sender_rank, receiver_rank, byte_count)
LogicCommPair = Tuple[int, int, int]
# A schedule is a list of phases, each phase is a list of `LogicCommPair`s.
LogicCommPairsByPhase = List[List[LogicCommPair]]


AVAILABLE_ALGOS = ["ar_ring", "ar_nhr", "ar_rhd", "a2a_pairwise", "a2a_scatter"]


def print_logic_comm_pairs_by_phase(logic_comm_pairs: LogicCommPairsByPhase, *, title: str | None = None) -> None:
    """Print per-phase (sender, receiver, bytes) pairs and traffic volume."""
    if title:
        print(title)

    total_bytes_all = 0
    for phase_id, phase_pairs in enumerate(logic_comm_pairs):
        phase_bytes = sum(int(p[2]) for p in phase_pairs)
        total_bytes_all += phase_bytes
        print(f"\n[phase {phase_id}] pairs={len(phase_pairs)} phase_bytes={phase_bytes}")
        for sender, receiver, trans_byte in phase_pairs:
            print(f"  ({sender} -> {receiver}, {int(trans_byte)} bytes)")

    print(f"\n[total] phases={len(logic_comm_pairs)} total_bytes={total_bytes_all}")


def schedule_to_logic_comm_pairs(schedule: Schedule) -> LogicCommPairsByPhase:
    """Convert a Schedule object to LogicCommPairsByPhase format."""
    result: LogicCommPairsByPhase = []
    for phase in schedule.phases:
        phase_pairs: List[LogicCommPair] = []
        for rank_op in phase.rank_ops:
            # Each rank sends to send_to with tx_bytes
            pair: LogicCommPair = (rank_op.rank, rank_op.send_to, rank_op.tx_bytes)
            phase_pairs.append(pair)
        result.append(phase_pairs)
    return result


def generate_ar_ring_logic_comm_pairs(n_comm_size: int, n_byte: int) -> LogicCommPairsByPhase:
    """Ring AllReduce schedule (logical ranks) - delegates to ring.py."""
    schedule = build_ar_ring_schedule(int(n_comm_size), int(n_byte))
    return schedule_to_logic_comm_pairs(schedule)


def generate_ar_RHD_logic_comm_pairs(n_comm_size: int, n_byte: int) -> LogicCommPairsByPhase:
    """Recursive halving/doubling (RHD) AllReduce - delegates to recursive_hd.py."""
    schedule = build_ar_rhd_schedule(int(n_comm_size), int(n_byte))
    return schedule_to_logic_comm_pairs(schedule)


def generate_ar_NHR_logic_comm_pairs(n_comm_size: int, n_byte: int) -> LogicCommPairsByPhase:
    """NHR AllReduce (ReduceScatter + AllGather) - delegates to nhr.py."""
    schedule = build_nhr_schedule(int(n_comm_size), int(n_byte))
    return schedule_to_logic_comm_pairs(schedule)


def generate_a2a_pairwise_logic_comm_pairs(n_comm_size: int, n_byte: int) -> LogicCommPairsByPhase:
    """Pairwise All2All schedule (logical ranks)."""
    n_total_phase = int(n_comm_size) - 1
    logic_rank_table = [i for i in range(int(n_comm_size))]
    pw_logic_comm_pairs: LogicCommPairsByPhase = []
    for phase_id in range(n_total_phase):
        phase_comm_pair: List[LogicCommPair] = []
        phase_byte = n_byte / n_comm_size
        send_gap = phase_id + 1
        for r in logic_rank_table:
            send_pair: LogicCommPair = (r, (r + send_gap) % len(logic_rank_table), int(phase_byte))
            phase_comm_pair.append(send_pair)
        pw_logic_comm_pairs.append(phase_comm_pair)
    return pw_logic_comm_pairs


def generate_a2a_scatter_logic_comm_pairs(n_comm_size: int, n_byte: int, k: int) -> LogicCommPairsByPhase:
    """All2All scatter schedule: merge every k pairwise phases into one phase."""
    # Start with the base pairwise All-to-All phases, then merge consecutive blocks of k stages
    pw_logic_comm_pairs = generate_a2a_pairwise_logic_comm_pairs(n_comm_size, n_byte)
    n_phases = len(pw_logic_comm_pairs)
    out: LogicCommPairsByPhase = []
    for i in range(0, n_phases, int(k)):
        merged: List[LogicCommPair] = []
        for stage in pw_logic_comm_pairs[i : i + int(k)]:
            merged.extend(stage)
        out.append(merged)
    return out


def generate_logic_comm_pairs(*, algo: str, comm_size: int, comm_bytes: int, scatter_k: int = 1) -> LogicCommPairsByPhase:
    """Unified entry: generate per-phase logical comm pairs for an algo."""
    if algo not in AVAILABLE_ALGOS:
        raise ValueError(f"Unsupported algo: {algo}. Supported: {AVAILABLE_ALGOS}")

    if algo == "ar_ring":
        return generate_ar_ring_logic_comm_pairs(comm_size, comm_bytes)
    if algo == "a2a_pairwise":
        return generate_a2a_pairwise_logic_comm_pairs(comm_size, comm_bytes)
    if algo == "a2a_scatter":
        if not (1 <= int(scatter_k) < int(comm_size)):
            raise ValueError("a2a_scatter requires scatter_k in range [1, comm_size)")
        return generate_a2a_scatter_logic_comm_pairs(comm_size, comm_bytes, int(scatter_k))
    if algo == "ar_nhr":
        return generate_ar_NHR_logic_comm_pairs(comm_size, comm_bytes)
    if algo == "ar_rhd":
        return generate_ar_RHD_logic_comm_pairs(comm_size, comm_bytes)

    raise ValueError(f"Unsupported algo: {algo}")


def write_ns3_traffic_csv(
    output_dir: Path,
    comm_domains: List[List[int]],
    logic_comm_pairs: LogicCommPairsByPhase,
    *,
    priority: int = 7,
    delay: str = "0ns",
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    traffic_path = output_dir / "traffic.csv"
    with traffic_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "taskId",
            "sourceNodeId",
            "destNodeId",
            "dataSize(Byte)",
            "opType",
            "priority",
            "delay",
            "phaseId",
            "dependOnPhases",
        ])

        task_id = 0
        for domain in comm_domains:
            for phase_id, phase_pairs in enumerate(logic_comm_pairs):
                for src_rank, dst_rank, byte_count in phase_pairs:
                    writer.writerow([
                        task_id,
                        domain[src_rank],
                        domain[dst_rank],
                        int(byte_count),
                        "URMA_WRITE",
                        priority,
                        delay,
                        phase_id,
                        "",
                    ])
                    task_id += 1

    return traffic_path


def write_netisim_rdma_operates(
    output_dir: Path,
    comm_domains: List[List[int]],
    logic_comm_pairs: LogicCommPairsByPhase,
    *,
    priority: int = 7,
) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for old_rdma_path in output_dir.glob("rdma_operate*.txt"):
        old_rdma_path.unlink()

    rdma_paths = []
    for domain_id, domain in enumerate(comm_domains):
        rdma_name = "rdma_operate.txt" if domain_id == 0 else f"rdma_operate{domain_id}.txt"
        rdma_path = output_dir / rdma_name
        rdma_paths.append(rdma_path)
        with rdma_path.open("w", encoding="utf-8") as f:
            f.write("stat rdma operate:\n")
            for phase_pairs in logic_comm_pairs:
                f.write("phase\n")
                for src_rank, dst_rank, byte_count in phase_pairs:
                    f.write(
                        "Type:rdma_send, "
                        f"src_node:{domain[src_rank]}, src_port:0, "
                        f"dst_node:{domain[dst_rank]}, dst_port:0, "
                        f"priority:{priority}, msg_len:{int(byte_count)}\n"
                    )

    return rdma_paths


if __name__ == "__main__":
    algo = "a2a_pairwise"
    traffic_sizes = [
        ("64MB", 64 * 1024 * 1024),
        ("256MB", 256 * 1024 * 1024),
    ]
    priority = 7
    delay = "0ns"
    cases = [
        [
            [0, 1], [2, 3], [4, 5], [6, 7],
            [8, 9], [10, 11], [12, 13], [14, 15],
        ],
        [
            [0, 2, 4, 6], [1, 3, 5, 7],
            [8, 10, 12, 14], [9, 11, 13, 15],
        ],
        [
            [0, 8], [1, 9], [2, 10], [3, 11],
            [4, 12], [5, 13], [6, 14], [7, 15],
        ],
    ]

    output_base = Path(__file__).resolve().parent / "output"
    for size_label, comm_bytes in traffic_sizes:
        output_root = output_base / f"netisim_a2a_pairwise_3cases_{size_label}"
        for case_id, comm_domains in enumerate(cases):
            comm_size = len(comm_domains[0])
            if any(len(domain) != comm_size for domain in comm_domains):
                raise ValueError(f"case{case_id} has mixed communication domain sizes")

            output_dir = output_root / f"case{case_id}"
            logic_comm_pairs = generate_logic_comm_pairs(
                algo=algo,
                comm_size=comm_size,
                comm_bytes=comm_bytes,
            )

            traffic_path = write_ns3_traffic_csv(
                output_dir,
                comm_domains,
                logic_comm_pairs,
                priority=priority,
                delay=delay,
            )
            rdma_paths = write_netisim_rdma_operates(
                output_dir,
                comm_domains,
                logic_comm_pairs,
                priority=priority,
            )

            print_logic_comm_pairs_by_phase(logic_comm_pairs, title=f"{size_label} case{case_id} {algo} logic comm pairs")
            print(f"{size_label} case{case_id} comm_domains: {comm_domains}")
            print(f"{size_label} case{case_id} traffic.csv written to: {traffic_path}")
            for rdma_path in rdma_paths:
                print(f"{size_label} case{case_id} {rdma_path.name} written to: {rdma_path}")
