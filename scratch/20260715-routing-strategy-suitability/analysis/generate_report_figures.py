#!/usr/bin/env python3
"""Generate the Chinese routing-strategy report figures from audited summaries."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager


HERE = Path(__file__).resolve().parent
MAIN_CSV = HERE / "summary.csv"
FOLLOWUP_CSV = (
    HERE.parent.parent / "20260715-routing-strategy-suitability-followup" / "analysis" / "summary.csv"
)
FIGURE_DIR = HERE / "figures"

COLORS = {
    "HASH64": "#3465A4",
    "CRC32": "#C44E52",
    "TOEPLITZ": "#3A923A",
    "ROUND_ROBIN": "#E17C05",
    "ADAPTIVE": "#7A5195",
    "INGRESS_PORT_STRIPE": "#008B8B",
    "CTP": "#3465A4",
    "LDST": "#E17C05",
}
MARKERS = {
    "HASH64": "o",
    "CRC32": "s",
    "TOEPLITZ": "^",
    "ROUND_ROBIN": "D",
    "ADAPTIVE": "P",
    "INGRESS_PORT_STRIPE": "X",
}


def configure_style() -> str:
    candidates = ["PingFang SC", "Hiragino Sans GB", "Arial Unicode MS", "Heiti SC"]
    installed = {font.name for font in font_manager.fontManager.ttflist}
    font = next((name for name in candidates if name in installed), "DejaVu Sans")
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [font, "DejaVu Sans"],
            "axes.unicode_minus": False,
            "svg.fonttype": "none",
            "svg.hashsalt": "openusim-routing-strategy-report",
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#666666",
            "axes.grid": True,
            "grid.color": "#D9D9D9",
            "grid.linewidth": 0.6,
            "grid.alpha": 0.7,
            "axes.axisbelow": True,
            "legend.frameon": False,
        }
    )
    return font


def save_figure(fig: plt.Figure, stem: str) -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "svg"):
        metadata = {"Date": None} if suffix == "svg" else None
        fig.savefig(
            FIGURE_DIR / f"{stem}.{suffix}",
            dpi=180,
            bbox_inches="tight",
            metadata=metadata,
        )
        if suffix == "svg":
            path = FIGURE_DIR / f"{stem}.{suffix}"
            normalized = "\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n"
            path.write_text(normalized)
    plt.close(fig)


def plot_hash_regret(main: pd.DataFrame) -> None:
    data = main.loc[main["block_id"].eq("hash-robustness")].copy()
    data["best_p95_us"] = data.groupby("comparison_cell")["p95_task_duration_us"].transform("min")
    data["regret_pct"] = (data["p95_task_duration_us"] / data["best_p95_us"] - 1.0) * 100.0

    def cell_label(row: pd.Series) -> str:
        prefix = "象流" if row["workload_profile"] == "hash-elephant" else f"{int(row['candidate_width'])} 路"
        return f"{prefix}\n种子 {int(row['traffic_seed'])}"

    data["cell_label"] = data.apply(cell_label, axis=1)
    ordered = []
    for width in (3, 5, 8):
        ordered.extend([f"{width} 路\n种子 {seed}" for seed in (11, 29, 47)])
    ordered.extend([f"象流\n种子 {seed}" for seed in (11, 29, 47)])
    selectors = ["HASH64", "CRC32", "TOEPLITZ"]
    matrix = data.pivot(index="selector", columns="cell_label", values="regret_pct").loc[
        selectors, ordered
    ]

    fig, ax = plt.subplots(figsize=(12.2, 3.6), constrained_layout=True)
    image = ax.imshow(matrix.to_numpy(), cmap="YlOrRd", vmin=0, aspect="auto")
    ax.grid(False)
    ax.set_title("Hash 稳健性：相对同场景最优 p95 FCT 的损失")
    ax.set_xticks(range(len(ordered)), ordered, fontsize=8)
    ax.set_yticks(range(len(selectors)), selectors)
    for row in range(matrix.shape[0]):
        for col in range(matrix.shape[1]):
            value = matrix.iloc[row, col]
            ax.text(col, row, f"{value:.1f}%", ha="center", va="center", fontsize=7.5)
    colorbar = fig.colorbar(image, ax=ax, pad=0.015)
    colorbar.set_label("p95 FCT regret (%)，越低越好")
    save_figure(fig, "01-hash-regret-heatmap")


def plot_spray_crossover(main: pd.DataFrame) -> None:
    data = main.loc[main["block_id"].eq("spray-crossover")].copy()
    data["profile"] = np.select(
        [
            data["routing_type"].eq("PER_FLOW_SHORTEST_PATHS"),
            data["selector"].eq("ROUND_ROBIN"),
        ],
        ["逐流 HASH64", "逐包 RR"],
        default="逐包 HASH64",
    )
    delay_order = ["20ns", "2us", "20us"]
    size_order = [(16384, "16 KiB"), (262144, "256 KiB"), (8388608, "8 MiB")]
    profiles = ["逐流 HASH64", "逐包 HASH64", "逐包 RR"]
    profile_style = {
        "逐流 HASH64": (COLORS["HASH64"], "o", "-"),
        "逐包 HASH64": ("#8DA0CB", "s", "--"),
        "逐包 RR": (COLORS["ROUND_ROBIN"], "D", "-"),
    }
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.0), sharey=True, constrained_layout=True)
    x = np.arange(len(delay_order))
    for ax, (size, title) in zip(axes, size_order):
        subset = data.loc[data["flow_size_bytes"].eq(size)]
        for profile in profiles:
            series = subset.loc[subset["profile"].eq(profile)].set_index("path_delay").loc[delay_order]
            color, marker, line = profile_style[profile]
            ax.plot(
                x,
                series["p95_task_duration_us"],
                label=profile,
                color=color,
                marker=marker,
                linestyle=line,
                linewidth=1.8,
                markersize=5,
            )
        ax.set_title(title)
        ax.set_xticks(x, ["20 ns", "2 us", "20 us"])
        ax.set_xlabel("慢路径附加时延")
        ax.set_yscale("log")
    axes[0].set_ylabel("p95 FCT (us，对数刻度)")
    axes[-1].legend(loc="upper left", bbox_to_anchor=(1.02, 1.0))
    fig.suptitle("Packet Spray crossover：流越短、时延偏斜越大，逐包收益越容易反转")
    save_figure(fig, "02-packet-spray-crossover")


def plot_adaptive_region(main: pd.DataFrame, followup: pd.DataFrame) -> None:
    dense = main.loc[
        main["block_id"].eq("adaptive-signal")
        & main["workload_profile"].eq("adaptive-screen")
        & main["interarrival_gap_ns"].eq(0)
    ].copy()
    confirm = main.loc[
        main["block_id"].eq("adaptive-signal")
        & main["workload_profile"].eq("adaptive-confirm")
    ].copy()
    sparse = followup.loc[followup["block_id"].eq("adaptive-single-packet-sparse")].copy()
    selectors = ["HASH64", "ROUND_ROBIN", "ADAPTIVE"]
    labels = {"HASH64": "HASH64", "ROUND_ROBIN": "RR", "ADAPTIVE": "Adaptive"}

    fig, axes = plt.subplots(1, 2, figsize=(12.8, 4.4), constrained_layout=True)
    ax = axes[0]
    x_order = [1.0, 0.5, 0.25]
    for selector in selectors:
        series = dense.loc[dense["selector"].eq(selector)].set_index("path_rate_ratio").loc[x_order]
        ax.plot(
            range(3),
            series["p95_task_duration_us"],
            label=labels[selector],
            color=COLORS[selector],
            marker=MARKERS[selector],
            linewidth=1.8,
        )
        replicate = confirm.loc[confirm["selector"].eq(selector), "p95_task_duration_us"]
        ax.scatter(
            np.full(len(replicate), 1),
            replicate,
            color=COLORS[selector],
            marker=MARKERS[selector],
            s=24,
            alpha=0.35,
        )
    ax.set_xticks(range(3), ["1.0", "0.5", "0.25"])
    ax.set_xlabel("慢路径速率 / 正常路径速率")
    ax.set_ylabel("p95 FCT (us)")
    ax.set_title("持续密集流量：慢路径越弱，Adaptive 优势越明显")
    ax.legend()

    ax = axes[1]
    gaps = [1000, 10000, 100000]
    x = np.arange(len(gaps))
    offsets = {"HASH64": -0.12, "ROUND_ROBIN": 0.0, "ADAPTIVE": 0.12}
    for selector in selectors:
        subset = sparse.loc[sparse["selector"].eq(selector)]
        grouped = subset.groupby("interarrival_gap_ns")["max_path_share"]
        means = grouped.mean().loc[gaps]
        ax.plot(
            x,
            means,
            label=labels[selector],
            color=COLORS[selector],
            marker=MARKERS[selector],
            linewidth=1.8,
        )
        for index, gap in enumerate(gaps):
            values = subset.loc[subset["interarrival_gap_ns"].eq(gap), "max_path_share"]
            ax.scatter(
                np.full(len(values), x[index] + offsets[selector]),
                values,
                color=COLORS[selector],
                marker=MARKERS[selector],
                s=20,
                alpha=0.35,
            )
    ax.set_xticks(x, ["1", "10", "100"])
    ax.set_xlabel("单包任务间隔 (us)")
    ax.set_ylabel("最大路径占比")
    ax.set_ylim(0.28, 1.05)
    ax.set_title("队列完全排空：Adaptive 固定选择首个并列候选")
    ax.legend()
    fig.suptitle("Adaptive 的信号边界：它响应持续负载差，不等同于通用均衡器")
    save_figure(fig, "03-adaptive-signal-region")


def plot_ingress_entropy(main: pd.DataFrame) -> None:
    data = main.loc[main["block_id"].eq("ingress-entropy")].copy()
    selectors = ["HASH64", "INGRESS_PORT_STRIPE"]
    labels = {"HASH64": "HASH64", "INGRESS_PORT_STRIPE": "Ingress Stripe"}
    x_order = [1, 2, 4, 8]
    fig, axes = plt.subplots(1, 2, figsize=(11.8, 4.2), constrained_layout=True)
    for selector in selectors:
        subset = data.loc[data["selector"].eq(selector)]
        color = COLORS[selector]
        marker = MARKERS[selector]
        for ax, metric in zip(axes, ["p95_task_duration_us", "path_jain"]):
            means = subset.groupby("active_ingress_count")[metric].mean().loc[x_order]
            ax.plot(
                x_order,
                means,
                color=color,
                marker=marker,
                linewidth=1.8,
                label=labels[selector],
            )
            for count in x_order:
                values = subset.loc[subset["active_ingress_count"].eq(count), metric]
                ax.scatter(
                    np.full(len(values), count),
                    values,
                    color=color,
                    marker=marker,
                    s=22,
                    alpha=0.3,
                )
    axes[0].set_title("完成时延")
    axes[0].set_ylabel("p95 FCT (us)")
    axes[1].set_title("路径均衡度")
    axes[1].set_ylabel("Path Jain index")
    axes[1].set_ylim(0.1, 1.04)
    for ax in axes:
        ax.set_xticks(x_order)
        ax.set_xlabel("活跃 ingress 端口数")
        ax.legend()
    fig.suptitle("Ingress Stripe 的收益依赖入口身份熵；单入口时映射塌缩")
    save_figure(fig, "04-ingress-stripe-boundary")


def plot_all_paths_tradeoff(followup: pd.DataFrame) -> None:
    data = followup.loc[
        followup["block_id"].eq("per-flow-all-distinct-keys")
        & followup["routing_type"].eq("PER_FLOW_ALL_PATHS")
    ].copy()
    data["regime"] = data["topology_profile"].str.replace("clos-distinct-", "", regex=False)
    regimes = ["neutral", "capacity", "latency"]
    regime_labels = ["等价额外路径", "额外容量", "20 us 绕行"]
    metrics = ["p95_fct_delta_vs_control_pct", "goodput_delta_vs_control_pct"]
    titles = ["p95 FCT 相对 shortest 的变化", "Goodput 相对 shortest 的变化"]
    fig, axes = plt.subplots(1, 2, figsize=(11.8, 4.3), constrained_layout=True)
    x = np.arange(len(regimes))
    for ax, metric, title in zip(axes, metrics, titles):
        for seed in (11, 29, 47):
            series = data.loc[data["pairing_seed"].eq(seed)].set_index("regime").loc[regimes]
            ax.plot(
                x,
                series[metric],
                marker="o",
                linewidth=1.4,
                label=f"配对种子 {seed}",
            )
        ax.axhline(0, color="#333333", linewidth=0.9)
        ax.set_xticks(x, regime_labels)
        ax.set_ylabel("相对变化 (%)")
        ax.set_title(title)
    axes[0].text(0.02, 0.04, "负值表示 FCT 改善", transform=axes[0].transAxes, fontsize=9)
    axes[1].text(0.02, 0.04, "正值表示 Goodput 改善", transform=axes[1].transAxes, fontsize=9)
    axes[1].legend(loc="upper right")
    fig.suptitle("PER_FLOW_ALL_PATHS：额外容量有价值，但高时延 detour 会反噬")
    save_figure(fig, "05-all-paths-tradeoff")


def plot_transport_transfer(main: pd.DataFrame) -> None:
    data = main.loc[main["block_id"].eq("transport-transfer")].copy()
    data["profile"] = np.select(
        [
            data["selector"].eq("HASH64") & data["routing_type"].eq("PER_FLOW_SHORTEST_PATHS"),
            data["selector"].eq("CRC32"),
            data["selector"].eq("TOEPLITZ"),
            data["selector"].eq("ROUND_ROBIN"),
            data["selector"].eq("ADAPTIVE"),
            data["selector"].eq("INGRESS_PORT_STRIPE"),
        ],
        ["流/H64", "流/CRC", "流/Toeplitz", "包/RR", "包/Adaptive", "流/Stripe"],
        default="包/ALL/H64",
    )
    profiles = ["流/H64", "流/CRC", "流/Toeplitz", "包/RR", "包/Adaptive", "流/Stripe", "包/ALL/H64"]
    transports = ["CTP", "LDST"]
    fig, axes = plt.subplots(1, 2, figsize=(13.0, 4.4), constrained_layout=True)
    x = np.arange(len(profiles))
    width = 0.36
    for index, transport in enumerate(transports):
        subset = data.loc[data["transport"].eq(transport)].set_index("profile").loc[profiles]
        offset = (index - 0.5) * width
        axes[0].bar(
            x + offset,
            subset["unique_branch_ports"],
            width,
            label=transport,
            color=COLORS[transport],
            alpha=0.88,
        )
        axes[1].bar(
            x + offset,
            subset["path_jain"],
            width,
            label=transport,
            color=COLORS[transport],
            alpha=0.88,
        )
    axes[0].set_ylabel("实际使用的分支路径数")
    axes[0].set_yticks([0, 1, 2, 3])
    axes[0].set_ylim(0, 3.2)
    axes[0].set_title("路径使用数量")
    axes[1].set_ylabel("Path Jain index")
    axes[1].set_ylim(0, 1.05)
    axes[1].set_title("路径选择签名")
    for ax in axes:
        ax.set_xticks(x, profiles, rotation=25, ha="right")
        ax.legend()
    fig.suptitle("CTP / LDST 迁移：逐流保持单路径，逐包策略使用三条路径")
    save_figure(fig, "06-ctp-ldst-transfer")


def main() -> None:
    font = configure_style()
    main_data = pd.read_csv(MAIN_CSV)
    followup_data = pd.read_csv(FOLLOWUP_CSV)
    if len(main_data) != 152 or len(followup_data) != 45:
        raise ValueError("Unexpected experiment row count; refusing to draw a partial matrix")
    plot_hash_regret(main_data)
    plot_spray_crossover(main_data)
    plot_adaptive_region(main_data, followup_data)
    plot_ingress_entropy(main_data)
    plot_all_paths_tradeoff(followup_data)
    plot_transport_transfer(main_data)
    print(f"Generated 6 PNG and 6 SVG figures in {FIGURE_DIR} using font {font}")


if __name__ == "__main__":
    main()
