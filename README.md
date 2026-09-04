# 无源 AOA 测向（MUSIC）

用圆阵 + USRP 估计无人机遥控/图传信号到达角。单站只出方位角；多站交汇/飞手定位仅预留接口。

**当前是 4 通道过渡态**：1 台 X310 + 2 块 TwinRX，固定接八元 UCA 的阵元 1、3、5、7。不是资料里的完整 8 路。第二台 X310 未部署。

## 文档

| 文件 | 内容 |
| --- | --- |
| [docs/interfaces.md](docs/interfaces.md) | 冻结的数据结构与 ZMQ/npy 格式 |
| [docs/hardware.md](docs/hardware.md) | 相参、接线、升级路径、分阶段指标 |
| [docs/runbook.md](docs/runbook.md) | 无设备回放 / 有 X310 采集 / 校准时机 |
| [AGENTS.md](AGENTS.md) | 如何开并行 Agent、目录所有权 |

硬件照片与 PDF 在 [`阵列天线/`](阵列天线/)（**只读**）。`优化结果/` 里「半径 xx mm」是单元相位中心，不是阵半径 `R_m`。

## 怎么开并行 Agent

见 [AGENTS.md](AGENTS.md)：一人一目录（`sdr` / `detect` / `aoa` / `host` …）。不要改 `docs/interfaces.md` 字段，除非明确要求。Cursor 规则在 `.cursor/rules/`。

## Python

- 基准：**3.11 x64**（`>=3.11,<3.14`）。
- `pip install -r requirements-dev.txt` 用于 replay / 将来的 host。
- **live UHD 不要 pip 装进默认清单**；Windows 用 Ettus 安装包或 `conda-forge::uhd`，建议 3.11 环境。Anaconda 3.13 可以跑仿真与回放。

本仓库目前只有目录骨架与文档，**没有** MUSIC、UHD 采集或 Qt 窗口实现。
