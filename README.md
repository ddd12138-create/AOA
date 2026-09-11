# 无源 AOA 测向（MUSIC）

用圆阵 + USRP 估计无人机遥控/图传信号到达角。单站只出方位角；多站交汇 / 飞手定位仅预留接口，`GeoFix.valid` 必须为 false。

**当前是 4 通道过渡态**：1 台 X310 + 2 块 TwinRX，固定接八元 UCA 的阵元 1、3、5、7。不是资料里的完整 8 路。第二台 X310 未部署。

## 现状

Worker 进程已接通 `sdr → detect → aoa`，Host 是独立的 PySide6 ZMQ 客户端。无设备时用 `--replay` 回放金标快拍即可跑通 MUSIC 与 GUI。

| 模块 | 状态 |
| --- | --- |
| `sdr/` | live（X310，需 UHD）与 `--replay`（npy + meta） |
| `detect/` | 900 MHz / 2.4 GHz / 5.8 GHz 能量检测 |
| `aoa/` | MUSIC，默认 M=4；`R_m` 为空则不出方位 |
| `host/` | PySide6 极坐标方位、IQ 摘要、未校准横幅 |
| `calib/` | 已知方位回放估计幅相；`identity.yaml` 表示未校准 |
| `sim/` | 生成 θ=30° 金标 `tests/golden/theta30_m4` |
| `geo/` | 预留，单站不填飞手经纬度 |

## 架构

```text
Worker（scripts/worker.py）              Host（scripts/host.py）
sdr → detect → aoa.MusicEstimator        PySide6 / pyqtgraph
        │ PUB  iq / detect / aoa / status
        │ tcp://127.0.0.1:5556
        │
        │ REP  tune / start / stop
        │ tcp://127.0.0.1:5557
```

MUSIC 与 UHD 只在 Worker 里跑。GUI 线程禁止测向或采集。

## Python

- 基准：**3.11 x64**（`>=3.11,<3.14`）。
- 回放 / GUI / 测试：`pip install -r requirements-dev.txt`。
- **live UHD 不要 pip 装进默认清单**。Windows 用 Ettus 安装包或 `conda-forge::uhd`，建议 3.11。Anaconda 3.13 可以跑仿真与回放。

```text
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
```

## 快速开始（无设备）

先生成金标（若 `tests/golden/theta30_m4.npy` 不存在）：

```text
python -m sim
```

终端 1 — Worker 回放（默认阵列 `configs/array_uca_m4_sim.yaml`）：

```text
python scripts/worker.py --replay tests/golden/theta30_m4
```

终端 2 — Host：

```text
python scripts/host.py --zmq tcp://127.0.0.1:5556
```

期望：极坐标指针约 **30°**，`azimuth_deg` ≈ 30，红色 **UNCALIBRATED** 横幅，`GeoFix.valid=false`。

无界面验收：

```text
pytest tests/test_aoa_theta30.py tests/test_worker_replay_theta30.py tests/test_calib_theta30.py
```

其它入口：

```text
python -m sdr --replay tests/golden/theta30_m4
python -m calib --replay tests/golden/theta30_m4 --theta-deg 30 --array configs/array_uca_m4_sim.yaml --out calib/sim_theta30.yaml
python scripts/worker.py --replay tests/golden/theta30_m4 --array configs/array_uca_m4.yaml
```

硬件夹具文件 `configs/array_uca_m4.yaml` 在 `R_m: null` 时仍 PUB `iq` / `detect`，不 PUB `aoa`，`status.state` 保持 `running` 并带缺半径说明。

## 有 X310 时

1. 等长电缆接阵元 1/3/5/7，**LO 共享**，`configs/channel_map.yaml` 里 `lo_share: true`。
2. 夹具量完后把 `configs/array_uca_m4.yaml` 的 `R_m` 填成米。不要把 HFSS「半径 xx mm」抄进去。
3. Python 3.11 + 厂商 / conda 的 `uhd`。

```text
python scripts/worker.py --live --config configs/channel_map.yaml --array configs/array_uca_m4.yaml
python scripts/worker.py --live --config configs/channel_map.yaml --array configs/array_uca_m4.yaml --save captures/x310_m4
```

未测 `R_m` 时不要把 live 结果当方位。不要用 RF 开关轮询未接的 2/4/6/8 元。

## 约束

- 交叉模块 API 只认 [`docs/interfaces.md`](docs/interfaces.md)。不要擅自改字段、单位、坐标系、字节序。
- 单站只出阵列坐标系 `azimuth_deg`（0° = 阵元 1 / 阵列 0° 轴，俯视逆时针，[0, 360)）。不要画成飞手 lat/lon。
- 默认 **M=4**。`configs/array_uca_m8.yaml` 只是预留。
- `calib/identity.yaml` 保持 `status.uncalibrated=true`，不要覆盖成暗室结果。
- [`阵列天线/`](阵列天线/) 照片与 PDF **只读**。优化图里的毫米半径是单元相位中心，不是 `R_m`。

## 文档

| 文件 | 内容 |
| --- | --- |
| [docs/interfaces.md](docs/interfaces.md) | 冻结的数据结构与 ZMQ/npy 格式 |
| [docs/hardware.md](docs/hardware.md) | 相参、接线、升级路径、分阶段指标 |
| [docs/runbook.md](docs/runbook.md) | 无设备回放 / 有 X310 采集 / 校准时机 |
| [AGENTS.md](AGENTS.md) | 并行 Agent 分工与目录所有权 |
| [scripts/README.md](scripts/README.md) | worker / host 启动命令 |

Cursor 规则在 `.cursor/rules/`。改代码时一人一目录（`sdr` / `detect` / `aoa` / `host` …）。
