# 运行手册（提纲）

Replay 路径：worker 读 npy+meta，整帧当 burst，跑 `aoa.MusicEstimator`，PUB `aoa` / `status`。Host 只订阅读数，GUI 进程不跑 MUSIC。

依赖与解释器见仓库根 `README.md`、`requirements.txt`。数据结构见 `docs/interfaces.md`。

---

## 无硬件：仿真 / 回放

1. Python 3.11（或 3.13 仅 replay）虚拟环境，安装 `requirements-dev.txt`。
2. 将来用 `sim/` 生成已知 θ=30° 的 `tests/golden/theta30_m4.npy` + `.meta.json`（SNR≈20 dB，N≥1024，M=4，φ=`[0,90,180,270]`）。`R_m` 必须来自夹具配置，不是优化图毫米半径。
3. 启动 worker 回放（无 USRP）：

   ```text
   python scripts/worker.py --replay tests/golden/theta30_m4
   ```

   默认 `--array configs/array_uca_m4_sim.yaml`。硬件夹具文件 `configs/array_uca_m4.yaml` 在 `R_m: null` 时拒绝出方位，`status.state=error`。

4. 另开 host 订阅读方位（极坐标应指向约 30°）：

   ```text
   python scripts/host.py --zmq tcp://127.0.0.1:5556
   ```

5. 验收：`pytest tests/test_aoa_theta30.py tests/test_worker_replay_theta30.py`。期望 `|azimuth_deg - 30| ≤ 2°`。这是算法回归，不是外场 5° RMS 指标。 identity 校准时 `status.uncalibrated=true`。

`--replay` 在 sdr/worker CLI 上必须始终存在，这样没有设备也能开发。

---

## 有 X310：怎么采

1. 确认过渡态硬件：1×X310 + 2×TwinRX，等长电缆接阵元 1/3/5/7，**LO 共享**。步骤见 `docs/hardware.md`。
2. 填 `configs/channel_map.yaml` 的 `usrp_serial` / `device_args`，`replay_only: false`，`lo_share: true`。
3. 夹具量完后填 `configs/array_uca_m4.yaml` 的 `R_m`（米）。未填则不要跑 live MUSIC。
4. Python **3.11** + 厂商/`conda` 的 `uhd`（不在默认 pip 清单）。
5. 约定采集命令（未实现）：

   ```text
   python scripts/worker.py --live --config configs/channel_map.yaml --array configs/array_uca_m4.yaml
   ```

   同一 CLI 仍须带 `--replay` 能力。
6. 建议把原始帧存成 npy + meta，便于事后 `--replay` 与校准复查。stem 命名含 `fc`、时间、M。

不要用开关去扫未接的 2/4/6/8 元。不要启动第二台 X310 的代码路径，除非用户明确要做 8 路升级。

---

## 校准何时做

必须复校：

- 更换射频电缆或转接器
- 明显温漂或设备冷启动后相位不稳
- 搬站、阵列旋转、重装夹具
- 修改 `channel_map.yaml` 或阵元接线

未校准：使用 `calib/identity.yaml`，worker `status.uncalibrated=true`，host 必须显示 **uncalibrated**。不要把 identity 当成暗室结果。

校准源（实现阶段）：功分器注入或暗室已知方位。系数写入 `calib/` 新文件并改 `calib_path`，不要改 `docs/interfaces.md` 字段。

---

## Host

```text
python scripts/host.py --zmq tcp://127.0.0.1:5556
```

只显示方位 / 频谱摘要。单站 **禁止** 把 AOA 画成飞手经纬度。GUI 线程禁止跑 MUSIC 或 UHD。
