# Agent 规则

空仓库骨架：无源 AOA（MUSIC）测向。默认 **M=4**（X310 + 2×TwinRX，阵元 1/3/5/7）。完整 8 路只预留配置。

## 开并行 Agent

按模块各开一个 Agent，工作目录限制在该文件夹。不要开「全仓库实现 MUSIC+Qt+UHD」的单 Agent。

建议分工：

- Agent sdr：只改 `sdr/`（必须保留 `--replay`）
- Agent detect：只改 `detect/`
- Agent aoa：只改 `aoa/`（M 可变，默认 4；禁止把优化图毫米半径当 R）
- Agent host：只改 `host/`（PySide6；GUI 线程禁止 MUSIC/UHD）
- Agent calib / sim / geo / tests：只改自己的目录

命令与 ZMQ 约定可改 `scripts/` 的 README 对应实现，但不得改接口字段。

## 冻结

- **禁止**修改 `docs/interfaces.md` 的字段、单位、坐标系、字节序，除非用户明确要求。
- **禁止**修改 `阵列天线/` 下任何现有照片、PDF、优化图。
- 单站只出方位；`GeoFix.valid` 必须为 false。禁止把 AOA 画成飞手经纬度。
- 不要写 RF 开关轮询 8 元；不要假设已有第二台 X310。

## 目录所有权

| 目录 | 产出 | 禁止 |
| --- | --- | --- |
| `sdr/` | IqFrame，live 与 `--replay` | MUSIC、Qt |
| `detect/` | DetectionEvent | UHD、MUSIC、Qt |
| `aoa/` | AoAResult | Qt、UHD、有效 GeoFix |
| `calib/` | 幅相 YAML | 改 interfaces 字段 |
| `geo/` | 预留交汇，默认 invalid | 单站 lat/lon |
| `host/` | PySide6 显示与命令 | GUI 线程跑 MUSIC/UHD |
| `sim/` | 已知 θ 的 npy+meta | 在 sim 里做谱峰当验收 |
| `tests/` | pytest | 在测试里实现 MUSIC |
| `docs/` | 说明 | 擅自改 `interfaces.md` |
| `configs/` | yaml | 把 HFSS 半径填进 `R_m` |
| `scripts/` | worker/host 入口 | 把计算塞进 host 进程 |

## 运行时

Worker 进程：sdr → detect → aoa。Host 进程：ZMQ 客户端。详见 `docs/interfaces.md`。
