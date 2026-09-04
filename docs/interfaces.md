# 冻结接口

**后续所有 Agent 禁止私自改本文件的字段名、单位、坐标系、字节序。** 需要改口时，必须有用户一句明确授权。

`schema_version` 当前为 **1**。 bump 版本视为改接口，同样需要用户授权。

算法接口按阵元数 **M 可变**，仓库默认 **M=4**（阵元 1、3、5、7）。完整 8 路只是配置预留，不要按 PDF 表 1 假设已经有第二台 X310。

---

## 坐标系与单位

### 阵列方位角 `azimuth_deg`

- 单位：**度**。
- 0° = **阵列 0° 轴**（夹具上应做物理标记，与 `phi_deg[0]` / 阵元 1 对齐）。
- θ 与阵元角 φ_m 均按**俯视阵列、逆时针增加**，与资料公式 (2) 一致：

  \( a(\theta)_m = \exp\bigl(j 2\pi R/\lambda \cos(\theta-\varphi_m)\bigr) \)

- 搜索网格：θ ∈ **[0, 360)**，不要用 ±180°。
- 本字段**不是**导航真北方位，也**不是**经纬度。

### `north_offset_deg`

阵列 0° 轴相对真北的方位，导航习惯：**从正北顺时针转到阵列 0° 轴**，单位度，范围 [0, 360)。

由阵列方位换到「从正北顺时针」的来波真方位（host 可选显示，默认仍显示 `azimuth_deg`）：

```text
azimuth_north_cw_deg = (north_offset_deg - azimuth_deg) mod 360
```

未标定北向时 `north_offset_deg = 0`，不要把阵列角冒充真北。

### 俯仰 `elevation_deg`

可选。M=4 过渡态必须填 JSON `null`。禁止把占位值当成已测俯仰。

### IQ

- 数值类型：numpy `complex64` ≡ 每个样本两个 IEEE754 **little-endian float32**（先 I 后 Q）。
- 布局：`layout = "channel_first"`，shape **`(n_chan, n_samp)`**，C 序。
- 第 `i` 行对应 `channel_ids[i]`，必须与导向矢量 `a(θ)` 的第 `i` 个元素、`element_ids[i]` 一致。
- ZMQ 体长度：`n_chan * n_samp * 8` 字节，等于 `numpy.ndarray.tobytes()`（C 序）。

### 时间戳

`timestamp_utc_ns`：UTC Unix 历元以来的纳秒，**int64**（不是毫秒，不是本地时）。

### 站址（仅 geo 预留）

- 大地坐标：WGS84 `lat_deg` / `lon_deg` / `alt_m`。
- 局部交汇预留：站心 **ENU**（东、北、天，米）。
- **单站不得**用站址 + 一条 AOA 射线填写飞手经纬度，也不得在 host 上把单站结果画成地图点。

---

## IqFrame

多通道基带快拍。live 与 replay 共用同一套字段。

| 字段 | 类型 | 单位 / 约束 |
| --- | --- | --- |
| `schema_version` | int | 必须为 `1` |
| `frame_id` | uint64 | 进程内单调；replay 用文件内值 |
| `timestamp_utc_ns` | int64 | 本帧第一样本的 UTC 纳秒 |
| `fc_hz` | float64 | 调谐中心频率 Hz |
| `fs_hz` | float64 | 采样率 Hz |
| `n_chan` | int | M，默认 4 |
| `n_samp` | int | 每通道样本数 N |
| `dtype` | string | 必须 `"complex64"` |
| `layout` | string | 必须 `"channel_first"` |
| `endianness` | string | 必须 `"little"` |
| `channel_ids` | int[M] | 逻辑通道 0..M-1，与 `a(θ)` 行序一致 |
| `element_ids` | int[M] | 物理阵元号，默认 `[1, 3, 5, 7]` |
| `iq` | complex64[M, N] | 仅内存 / npy / ZMQ 体；**不要**放进 JSON |

JSON 头（ZMQ 第一帧或 sidecar）**不得**内嵌 `iq` 数组。

---

## 文件回放格式

一对文件共用 stem（无扩展名）：

```text
<path>/<stem>.npy
<path>/<stem>.meta.json
```

- `.npy`：NumPy 1.0/2.0 `np.save` 格式；`dtype=complex64`；`shape=(n_chan, n_samp)`；C 序。
- `.meta.json`：IqFrame **除 `iq` 外**的全部字段，UTF-8 JSON。`n_chan`/`n_samp` 必须与 npy shape 一致。

`--replay <stem>` 同时读这两个文件。禁止另搞一套自定义 IQ 二进制头。

---

## DetectionEvent

| 字段 | 类型 | 单位 / 约束 |
| --- | --- | --- |
| `schema_version` | int | `1` |
| `event_id` | uint64 | |
| `timestamp_utc_ns` | int64 | 事件标注时间（通常取 burst 起点） |
| `fc_hz` | float64 | Hz |
| `bw_hz` | float64 | 检测占用带宽 Hz |
| `snr_db` | float64 | dB |
| `burst_start_samp` | int | 相对 `iq_ref.frame_id` 的样本下标，含 |
| `burst_end_samp` | int | 半开区间：`[start, end)` |
| `burst_start_utc_ns` | int64 | UTC ns |
| `burst_end_utc_ns` | int64 | UTC ns |
| `iq_ref` | object | 见下 |
| `band` | string | `"900M"` \| `"2.4G"` \| `"5.8G"` |

`iq_ref`：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `frame_id` | uint64 | 指向 IqFrame |
| `start_samp` | int | 与 `burst_start_samp` 相同约定 |
| `end_samp` | int | 半开 |

不要复制整段 IQ 进 DetectionEvent。aoa 用 `iq_ref` 回查 worker 内缓存或 replay 切片。

---

## AoAResult

单站只输出方位（及可选俯仰占位）。

| 字段 | 类型 | 单位 / 约束 |
| --- | --- | --- |
| `schema_version` | int | `1` |
| `result_id` | uint64 | |
| `timestamp_utc_ns` | int64 | 与所用 burst 对齐 |
| `detection_event_id` | uint64 | |
| `azimuth_deg` | float64 | 阵列坐标系，[0, 360) |
| `elevation_deg` | float64 or null | M=4 必须 `null` |
| `confidence` | float64 | [0, 1] |
| `music_spectrum_summary` | object | 见下 |
| `M` | int | 本次用的通道数 |
| `element_ids` | int[M] | 与 IqFrame 一致 |
| `K_est` | int | 估计信源数；M=4 阶段评估 1～2，不要宣称 ≥3 |
| `geo_fix` | GeoFix | 单站必须 `valid=false` |

`music_spectrum_summary`：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `grid_start_deg` | float64 | 必须为 `0` |
| `grid_stop_deg` | float64 | 必须为 `360`（不含，与半开网格一致） |
| `grid_step_deg` | float64 | 如 `0.5`；应远小于 5° 指标 |
| `n_peaks` | int | |
| `peaks` | array | 元素 `{ "theta_deg": float, "p_db": float }`，按 p_db 降序 |

不要把整条 MUSIC 谱塞进 ZMQ JSON。完整谱仅 worker 内或调试文件。

---

## GeoFix（预留）

| 字段 | 类型 | 单站取值 |
| --- | --- | --- |
| `valid` | bool | **必须 `false`** |
| `lat_deg` | float64 or null | `null` |
| `lon_deg` | float64 or null | `null` |
| `alt_m` | float64 or null | `null` |
| `method` | string | `"none"` |
| `station_ids` | string[] | `[]` |
| `crs` | string | `"WGS84"`（预留） |
| `note` | string | `"single-station AOA must not populate GeoFix"` |

多站交汇以后才允许 `valid=true`。host 看到 `valid=false` 时禁止画飞手坐标。

---

## ChannelMap

逻辑通道 ↔ TwinRX 口 ↔ 物理阵元。改映射必须同步 `a(θ)` 行序，禁止只改线不改表。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | int | `1` |
| `M` | int | 默认 4 |
| `lo_share` | bool | 必须 `true` 才允许 live |
| `replay_only` | bool | `true` 时可忽略 USRP 序列号 |
| `device_args` | string | UHD 参数；replay 可空 |
| `usrp_serial` | string or null | replay 可为 `null` |
| `mapping` | object[] | 长度 = M，按下表 |

`mapping[]` 每个元素：

| 字段 | 类型 | 默认 M=4 |
| --- | --- | --- |
| `channel_index` | int | 0..M-1，等于 `a(θ)` 行号 |
| `element_id` | int | 1,3,5,7 |
| `usrp_chan` | string | `"A:0"` / `"A:1"` / `"B:0"` / `"B:1"` |
| `twinrx_slot` | string | `"A"` 或 `"B"` |
| `twinrx_rx` | int | 0 或 1 |

默认行序（与 `configs/channel_map.yaml` 一致）：

```text
channel_index 0  →  A:0  →  element 1  →  φ = 0°
channel_index 1  →  A:1  →  element 3  →  φ = 90°
channel_index 2  →  B:0  →  element 5  →  φ = 180°
channel_index 3  →  B:1  →  element 7  →  φ = 270°
```

---

## ArrayGeometry

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | int | `1` |
| `array_type` | string | `"UCA"` |
| `M` | int | 4 或预留 8 |
| `element_ids` | int[M] | 选出的阵元 |
| `R_m` | float64 or null | **UCA 阵半径，米**。未实测前必须 `null` |
| `phi_deg` | float64[M] | 俯视逆时针，相对阵列 0° 轴 |
| `north_offset_deg` | float64 | 见上 |
| `calib_path` | string | 相对仓库根，如 `calib/identity.yaml` |

`R_m` 填写：用夹具图纸或卷尺量 **阵列旋转中心 → 该单元约定参考点**（馈电点；若改用相位中心必须在本文件用户授权下加字段，不得偷换 `R_m` 含义）。

**禁止**把 `阵列天线/优化结果/` 里「半径 xx mm」（HFSS 单元相位中心 Offset）当成 `R_m`。那些毫米数不是圆阵半径。

`aoa` 在 `R_m is null` 时必须拒绝出方位，或仅输出带错误的 status，不得静默用 21.25 mm 等数。

---

## CalibFile

`ArrayGeometry.calib_path` 指向的 YAML。系数按 `channel_index` 乘到 `a(θ)` 各行（或等价地预均衡 IQ 行）。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | int | `1` |
| `M` | int | 须与 geometry 一致 |
| `channel_ids` | int[M] | 与 IqFrame 行序一致 |
| `gain_lin` | float64[M] | 线性电压增益，identity = 全 1 |
| `phase_rad` | float64[M] | 附加相位，弧度，identity = 全 0 |
| `status` | string | `"identity"` \| `"calibrated"` |
| `fc_hz` | float64 or null | 该套系数适用频点；identity 可为 `null` |

恒等校准见 `calib/identity.yaml`。使用 identity 时 worker `status` 与 host 必须标明 `uncalibrated`。

---

## ZMQ 信封

双进程：worker（sdr→detect→aoa）PUB，host SUB。另开 REQ/REP 命令口。

默认（可在实现时用 CLI 覆盖，但 topic 名冻结）：

| 角色 | 绑定 |
| --- | --- |
| PUB（worker） | `tcp://127.0.0.1:5556` |
| REP（worker 命令） | `tcp://127.0.0.1:5557` |

### PUB topic（UTF-8 字符串，multipart 第 0 帧）

| topic | 后续帧 | 载荷 |
| --- | --- | --- |
| `iq` | JSON 头；raw IQ | 头 = IqFrame 无 `iq`；体 = `complex64` C 序 bytes |
| `detect` | 单帧 JSON | DetectionEvent |
| `aoa` | 单帧 JSON | AoAResult；**禁止** `geo_fix.valid=true` |
| `status` | 单帧 JSON | 见下 |

`status` JSON：

```json
{
  "schema_version": 1,
  "timestamp_utc_ns": 0,
  "state": "idle",
  "replay": true,
  "M": 4,
  "fc_hz": 2400000000.0,
  "uncalibrated": true,
  "detail": ""
}
```

`state`：`"idle"` \| `"running"` \| `"error"`。

### REP 命令（JSON 一问一答）

请求：

```json
{ "cmd": "tune" | "start" | "stop", "fc_hz": null, "fs_hz": null, "gain_db": null }
```

- `tune`：可带 `fc_hz` / `fs_hz` / `gain_db`（Hz、Hz、dB）。
- `start` / `stop`：其余字段 `null`。
- 应答：`{ "ok": true, "error": null }` 或 `{ "ok": false, "error": "..." }`。

IQ **不得**用纯 JSON 数组传输。

---

## 进程划分（实现约束，不是字段）

- 进程 A：worker = sdr + detect + aoa。
- 进程 B：host = PySide6，只收 ZMQ、发命令。
- 同进程 Qt 信号槽传输 IQ/MUSIC **不作为本仓库架构**。
