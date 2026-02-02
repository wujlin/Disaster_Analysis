#!/usr/bin/env python3
"""
注意：该脚本是早期草稿，未保证与当前 `src/disaster/plot_style.py` 兼容。

现在推荐使用：
- 地图流线图（方案 A）：`scripts/intraband_flow_viz.py`
"""

raise SystemExit("已弃用：请改用 `scripts/intraband_flow_viz.py`（地图流线图）。")

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# 导入项目绘图风格
from disaster import plot_style as ps

def load_data(base_dir: Path) -> dict:
    """加载所有需要的CSV数据。"""
    data = {}
    
    # 50-100km 向心流的起点/目的地分布
    dest_dir = base_dir / "movement_destination_analysis" / "tables"
    data["origin_hist"] = pd.read_csv(dest_dir / "origin_distance_hist.csv")
    data["dest_hist"] = pd.read_csv(dest_dir / "destination_distance_hist.csv")
    
    # 25-50km 流入来源
    inflow_dir = base_dir / "movement_inflow_source_analysis" / "tables"
    data["inflow_source"] = pd.read_csv(inflow_dir / "inflow_source_by_band.csv")
    
    return data


def plot_origin_dest_comparison(origin: pd.DataFrame, dest: pd.DataFrame, out_path: Path) -> None:
    """绘制起点-目的地距离对比图。"""
    fig, ax = plt.subplots(figsize=(8, 5))
    
    # 只取有流量的部分
    origin_valid = origin[origin["flow_fraction"] > 0].copy()
    dest_valid = dest[dest["flow_fraction"] > 0].copy()
    
    width = 4  # bar宽度
    
    # 起点分布（蓝色）
    ax.bar(
        origin_valid["bin_center_km"] - width/2,
        origin_valid["flow_fraction"] * 100,
        width=width,
        label="起点 (Origin)",
        color=ps.COLORS["primary"],
        alpha=0.8,
        edgecolor="white",
        linewidth=0.5,
    )
    
    # 目的地分布（橙色）
    ax.bar(
        dest_valid["bin_center_km"] + width/2,
        dest_valid["flow_fraction"] * 100,
        width=width,
        label="目的地 (Destination)",
        color=ps.COLORS["secondary"],
        alpha=0.8,
        edgecolor="white",
        linewidth=0.5,
    )
    
    # 标注50-100km带的范围
    ax.axvspan(50, 100, alpha=0.1, color="gray", label="50-100km band")
    ax.axvline(50, color="gray", linestyle="--", linewidth=1, alpha=0.5)
    ax.axvline(100, color="gray", linestyle="--", linewidth=1, alpha=0.5)
    
    # 添加箭头示意流动方向
    ax.annotate(
        "",
        xy=(60, 30),  # 目的地峰值
        xytext=(80, 28),  # 起点位置
        arrowprops=dict(arrowstyle="->", color="black", lw=2),
    )
    ax.text(70, 32, "短程向心移动", ha="center", fontsize=10, style="italic")
    
    ax.set_xlabel("与震中距离 (km)")
    ax.set_ylabel("流量占比 (%)")
    ax.set_title("50-100km 带「向心流」的起点与目的地分布\n(Turkey, t=40h)")
    ax.legend(loc="upper right")
    ax.set_xlim(40, 110)
    ax.set_ylim(0, 40)
    
    # 添加关键发现注释
    ax.text(
        0.02, 0.98,
        "关键发现：起点和目的地都在 50-100km 带内\n→ 这是带内重组，不是跨区域救援",
        transform=ax.transAxes,
        fontsize=9,
        verticalalignment="top",
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
    )
    
    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    fig.savefig(out_path.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    print(f"已保存: {out_path}")


def plot_inflow_source_bars(inflow: pd.DataFrame, out_path: Path) -> None:
    """绘制流入来源分解条形图。"""
    fig, ax = plt.subplots(figsize=(7, 5))
    
    # 准备数据
    bands = inflow["start_band"].tolist()
    fractions = inflow["flow_fraction"].tolist()
    
    # 颜色映射
    colors = []
    for band in bands:
        if band == "25-50km":
            colors.append(ps.COLORS["highlight"])  # 高亮本带
        else:
            colors.append(ps.COLORS["muted"])
    
    bars = ax.barh(bands, [f * 100 for f in fractions], color=colors, edgecolor="white")
    
    # 添加数值标签
    for bar, frac in zip(bars, fractions):
        width = bar.get_width()
        if width > 1:
            ax.text(
                width - 0.5, bar.get_y() + bar.get_height()/2,
                f"{frac*100:.1f}%",
                ha="right", va="center", fontsize=11, fontweight="bold", color="white"
            )
        elif width > 0.01:
            ax.text(
                width + 0.5, bar.get_y() + bar.get_height()/2,
                f"{frac*100:.2f}%",
                ha="left", va="center", fontsize=9
            )
    
    ax.set_xlabel("流量占比 (%)")
    ax.set_title("25-50km 带流入来源分解\n(Turkey, t=40h)")
    ax.set_xlim(0, 105)
    
    # 添加关键发现注释
    ax.text(
        0.98, 0.02,
        "99.6% 是带内流动\n外部流入 < 0.4%",
        transform=ax.transAxes,
        fontsize=10,
        ha="right", va="bottom",
        bbox=dict(boxstyle="round", facecolor="salmon", alpha=0.3),
    )
    
    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    fig.savefig(out_path.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    print(f"已保存: {out_path}")


def plot_flow_schematic(out_path: Path) -> None:
    """绘制流动模式示意图：带内 vs 带间。"""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    
    # === 左图：我们预期的模式（跨区域救援） ===
    ax1 = axes[0]
    ax1.set_xlim(-1, 5)
    ax1.set_ylim(-0.5, 3)
    ax1.set_aspect("equal")
    ax1.axis("off")
    ax1.set_title("预期模式：跨区域流动", fontsize=12, fontweight="bold")
    
    # 画同心圆
    for r, label in [(0.5, "0-25km"), (1.2, "25-50km"), (2.2, "50-100km"), (3.5, "100km+")]:
        circle = plt.Circle((2, 1.5), r, fill=False, linestyle="--", color="gray", alpha=0.5)
        ax1.add_patch(circle)
        ax1.text(2 + r + 0.1, 1.5, label, fontsize=8, va="center")
    
    # 震中
    ax1.plot(2, 1.5, "r*", markersize=15)
    ax1.text(2, 1.2, "震中", ha="center", fontsize=9)
    
    # 预期的流动箭头（从外向内）
    ax1.annotate("", xy=(2.3, 1.5), xytext=(3.2, 1.5),
                 arrowprops=dict(arrowstyle="->", color="green", lw=2))
    ax1.text(2.75, 1.7, "救援?", color="green", fontsize=10, ha="center")
    
    ax1.annotate("", xy=(2, 2.0), xytext=(2, 2.8),
                 arrowprops=dict(arrowstyle="->", color="green", lw=2))
    
    # === 右图：实际观测的模式（带内重组） ===
    ax2 = axes[1]
    ax2.set_xlim(-1, 5)
    ax2.set_ylim(-0.5, 3)
    ax2.set_aspect("equal")
    ax2.axis("off")
    ax2.set_title("实际观测：带内短程流动", fontsize=12, fontweight="bold")
    
    # 画同心圆
    for r, label in [(0.5, "0-25km"), (1.2, "25-50km"), (2.2, "50-100km"), (3.5, "100km+")]:
        circle = plt.Circle((2, 1.5), r, fill=False, linestyle="--", color="gray", alpha=0.5)
        ax2.add_patch(circle)
        ax2.text(2 + r + 0.1, 1.5, label, fontsize=8, va="center")
    
    # 震中
    ax2.plot(2, 1.5, "r*", markersize=15)
    ax2.text(2, 1.2, "震中", ha="center", fontsize=9)
    
    # 实际的流动箭头（带内短程）
    # 50-100km 带内
    ax2.annotate("", xy=(3.0, 2.0), xytext=(3.5, 2.3),
                 arrowprops=dict(arrowstyle="->", color="blue", lw=2))
    ax2.annotate("", xy=(3.2, 1.0), xytext=(3.7, 0.7),
                 arrowprops=dict(arrowstyle="->", color="blue", lw=2))
    
    # 25-50km 带内
    ax2.annotate("", xy=(2.5, 2.2), xytext=(2.8, 2.5),
                 arrowprops=dict(arrowstyle="->", color="blue", lw=1.5))
    
    # 高亮 50-100km 带
    ring = plt.matplotlib.patches.Annulus((2, 1.5), 2.2, 1.0, alpha=0.2, color="blue")
    ax2.add_patch(ring)
    
    ax2.text(3.8, 1.5, "99%\n带内", color="blue", fontsize=11, ha="center", fontweight="bold")
    
    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    fig.savefig(out_path.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    print(f"已保存: {out_path}")


def main():
    base_dir = Path(__file__).resolve().parents[1] / "outputs" / "turkiye_earthquake_2023"
    out_dir = base_dir / "intraband_flow_viz"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    print("加载数据...")
    data = load_data(base_dir)
    
    print("绘制起点-目的地对比图...")
    plot_origin_dest_comparison(
        data["origin_hist"],
        data["dest_hist"],
        out_dir / "origin_dest_comparison.png"
    )
    
    print("绘制流入来源分解图...")
    plot_inflow_source_bars(
        data["inflow_source"],
        out_dir / "inflow_source_breakdown.png"
    )
    
    print("绘制流动模式示意图...")
    plot_flow_schematic(out_dir / "flow_schematic.png")
    
    print(f"\n完成！所有图保存在: {out_dir}")


if __name__ == "__main__":
    main()
