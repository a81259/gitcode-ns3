"""Helpers for compacting routing-table ranges without changing route values."""

from __future__ import annotations

RouteTuple = tuple[str, str, int, str, str]

ROUTE_FIELDNAMES = {"nodeId", "dstNodeId", "dstPortId", "outPorts", "metrics"}


def parse_range(value: str) -> tuple[int, int]:
    if ".." in value:
        left, right = value.split("..", 1)
        return int(left), int(right)
    node_id = int(value)
    return node_id, node_id


def format_range(start: int, end: int) -> str:
    return str(start) if start == end else f"{start}..{end}"


def merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1] + 1:
            merged.append((start, end))
            continue
        prev_start, prev_end = merged[-1]
        merged[-1] = (prev_start, max(prev_end, end))
    return merged


def compact_route_rows(rows: list[RouteTuple]) -> list[RouteTuple]:
    by_dst_signature: dict[tuple[int, int, int, str, str], list[tuple[int, int]]] = {}
    for node_id, dst_id, dst_port, out_ports, metrics in rows:
        node_start, node_end = parse_range(str(node_id))
        dst_start, dst_end = parse_range(str(dst_id))
        key = (node_start, node_end, int(dst_port), str(out_ports), str(metrics))
        by_dst_signature.setdefault(key, []).append((dst_start, dst_end))

    compacted_rows: list[RouteTuple] = []
    for (node_start, node_end, dst_port, out_ports, metrics), intervals in by_dst_signature.items():
        for dst_start, dst_end in merge_intervals(intervals):
            compacted_rows.append((
                format_range(node_start, node_end),
                format_range(dst_start, dst_end),
                dst_port,
                out_ports,
                metrics,
            ))

    return sorted(
        compacted_rows,
        key=lambda row: (parse_range(row[0])[0], parse_range(row[1])[0], int(row[2])),
    )


def compact_route_dict_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    row_tuples = [
        (
            row["nodeId"],
            row["dstNodeId"],
            int(row["dstPortId"]),
            row["outPorts"],
            row["metrics"],
        )
        for row in rows
    ]
    return [
        {
            "nodeId": node_id,
            "dstNodeId": dst_id,
            "dstPortId": str(dst_port),
            "outPorts": out_ports,
            "metrics": metrics,
        }
        for node_id, dst_id, dst_port, out_ports, metrics in compact_route_rows(row_tuples)
    ]


def is_route_fieldset(fieldnames: list[str] | None) -> bool:
    return fieldnames is not None and ROUTE_FIELDNAMES.issubset(set(fieldnames))
