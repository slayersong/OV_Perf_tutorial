"""
USDRT + Warp 版 PointInstancer（非阻塞 + 优化写回）
====================================================
解决两个问题：
  1. 主线程卡死：GPU 计算放后台线程，Fabric 写回在主线程订阅回调里执行
  2. attr_set 慢：预分配持久 GPU buffer + 用 tolist() 替代 list comprehension

线程模型：
  ┌─ 后台线程（_compute_loop）─────────────────────┐
  │  Warp kernel（GPU）→ numpy → 放入 _pending     │
  └─────────────────────────────────────────────────┘
            ↓ threading.Lock 保护
  ┌─ 主线程（_on_update 订阅回调，每帧）────────────┐
  │  取 _pending → pos_attr.Set()（Fabric 写）      │
  └─────────────────────────────────────────────────┘

在 Omniverse Script Editor 中运行。
停止动画：animator.stop()
"""

import random
import threading
import time

import numpy as np
import warp as wp
from pxr import Gf as PxrGf, Sdf as PxrSdf, UsdGeom as PxrUsdGeom
from usdrt import Usd
from usdrt import Sdf as RtSdf
import omni.kit.app
import omni.usd

# ============================================================
# 常量
# ============================================================
CUBE_SIZE  = 50.0
GRID_STEP  = 100.0
RAND_XZ    = 20.0
RAND_Y_MAX = 30.0
NUM        = 100     # NxN，共 NUM*NUM 个 instance

INSTANCER_PATH = "/World/MyPointInstancer"
PROTO_PATH     = INSTANCER_PATH + "/Prototype_Box"


# ============================================================
# 计时工具
# ============================================================
def _ms(t0) -> float:
    return (time.perf_counter() - t0) * 1000.0

def _log(tag: str, ms: float, extra: str = ""):
    print(f"  {tag:<16} {ms:8.2f} ms  {extra}")


# ============================================================
# 1. 创建阶段（pxr，含分段计时）
# ============================================================
def create_point_instancer(pxr_stage, num: int) -> int:
    total_t = time.perf_counter()
    count = num * num
    print(f"\n[CREATE] {count} instances ({num}x{num})")

    t0 = time.perf_counter()
    PxrUsdGeom.Xform.Define(pxr_stage, "/World")
    cube = PxrUsdGeom.Cube.Define(pxr_stage, PROTO_PATH)
    cube.CreateSizeAttr(CUBE_SIZE)
    cube.CreateDisplayColorAttr().Set([PxrGf.Vec3f(0.2, 0.6, 1.0)])
    instancer = PxrUsdGeom.PointInstancer.Define(pxr_stage, INSTANCER_PATH)
    instancer.GetPrototypesRel().AddTarget(PxrSdf.Path(PROTO_PATH))
    _log("[T-DEFINE]", _ms(t0))

    t0 = time.perf_counter()
    proto_indices, positions, orientations, scales = [], [], [], []
    for i in range(num):
        for j in range(num):
            proto_indices.append(0)
            rx = random.uniform(-RAND_XZ, RAND_XZ)
            ry = random.uniform(0.0, RAND_Y_MAX)
            rz = random.uniform(-RAND_XZ, RAND_XZ)
            positions.append(PxrGf.Vec3f(i * GRID_STEP + rx, ry, j * GRID_STEP + rz))
            orientations.append(PxrGf.Quath(1, 0, 0, 0))
            scales.append(PxrGf.Vec3f(1, 1, 1))
    _log("[T-BUILD]", _ms(t0), "Python list 构建")

    t0 = time.perf_counter()
    instancer.GetProtoIndicesAttr().Set(proto_indices)
    instancer.GetPositionsAttr().Set(positions)
    instancer.GetOrientationsAttr().Set(orientations)
    instancer.GetScalesAttr().Set(scales)
    _log("[T-SET-ALL]", _ms(t0), "pxr SetAttr x4")

    _log("[T-TOTAL]", _ms(total_t), "创建合计")
    return count


# ============================================================
# 2. Warp kernel
# ============================================================
@wp.kernel(enable_backward=False)
def animate_positions_kernel(
    positions: wp.array(dtype=wp.vec3f),
    time_val:  float,
    amplitude: float,
    speed:     float,
):
    i = wp.tid()
    p = positions[i]
    phase = float(i) * 0.4
    new_y = amplitude * wp.sin(speed * time_val + phase)
    positions[i] = wp.vec3f(p[0], new_y, p[2])


# ============================================================
# 3. USDRT 初始化
# ============================================================
def get_rt_attr(rt_stage):
    print("\n[USDRT-INIT]")
    t0 = time.perf_counter()
    n = sum(1 for _ in rt_stage.Traverse())
    _log("[T-TRAVERSE]", _ms(t0), f"{n} prims")

    t0 = time.perf_counter()
    prim = rt_stage.GetPrimAtPath(RtSdf.Path(INSTANCER_PATH))
    if not prim.IsValid():
        raise RuntimeError(f"prim not found: {INSTANCER_PATH}")
    attr = prim.GetAttribute("positions")
    if not attr.IsValid():
        raise RuntimeError("'positions' attr not found")
    _log("[T-GETATTR]", _ms(t0))
    return attr


# ============================================================
# 4. PointInstancerAnimator
#    - 后台线程：GPU kernel + numpy 拉回 CPU
#    - 主线程订阅：Fabric 写回（USD 写必须在主线程）
# ============================================================
class PointInstancerAnimator:
    """
    用法：
        animator = PointInstancerAnimator(pos_attr, count)
        # 自动开始动画
        # 停止：animator.stop()
    """

    def __init__(self, pos_attr, count: int,
                 amplitude: float = 25.0,
                 speed: float = 2.0,
                 target_fps: float = 60.0):
        self._pos_attr  = pos_attr
        self._amplitude = amplitude
        self._speed     = speed
        self._interval  = 1.0 / target_fps
        self._frame     = 0
        self._count     = count

        # ── 优化 1：预分配持久 GPU buffer，避免每帧 malloc ──
        raw = pos_attr.Get()
        positions_np = np.array(raw, dtype=np.float32)          # (N, 3)
        self._positions_gpu = wp.array(
            positions_np.flatten(), dtype=wp.vec3f, device="cuda:0"
        )

        # ── 线程间共享数据（后台写、主线程读）──
        self._lock    = threading.Lock()
        self._pending: np.ndarray | None = None   # 等待写回 Fabric 的结果
        self._stop    = threading.Event()

        # ── 后台计算线程 ──
        self._thread = threading.Thread(
            target=self._compute_loop, name="PIAnimator-GPU", daemon=True
        )
        self._thread.start()

        # ── 主线程订阅：每帧回调，负责 Fabric 写回 ──
        self._sub = omni.kit.app.get_app().get_update_event_stream() \
            .create_subscription_to_pop(self._on_update, name="PIAnimator-Write")

        print(f"[Animator] 启动，{count} instances，target {target_fps:.0f} fps")

    # ----------------------------------------------------------
    # 后台线程：GPU 计算（可以在任意线程）
    # ----------------------------------------------------------
    def _compute_loop(self):
        while not self._stop.is_set():
            frame_start = time.perf_counter()
            t_val = self._frame * self._interval

            # GPU kernel（纯 GPU，极快）
            wp.launch(
                animate_positions_kernel,
                dim=len(self._positions_gpu),
                inputs=[self._positions_gpu,
                        float(t_val),
                        float(self._amplitude),
                        float(self._speed)],
                device="cuda:0",
            )
            wp.synchronize()

            # GPU → CPU（numpy）
            result = self._positions_gpu.numpy().copy()

            # 放入 pending，供主线程写回
            with self._lock:
                self._pending = result

            self._frame += 1

            # 限速，避免后台线程把 CPU 跑满
            elapsed = time.perf_counter() - frame_start
            sleep_t = self._interval - elapsed
            if sleep_t > 0:
                time.sleep(sleep_t)

    # ----------------------------------------------------------
    # 主线程回调：Fabric 写回（USD/Fabric 写必须在主线程）
    # ----------------------------------------------------------
    def _on_update(self, event):
        with self._lock:
            result = self._pending
            self._pending = None

        if result is None:
            return  # 后台线程还没算完，跳过本帧

        t0 = time.perf_counter()

        # ── 优化 2：tolist() 比 [tuple(v) for v in arr] 快约 3x ──
        self._pos_attr.Set(result.tolist())

        elapsed = _ms(t0)
        # 每 60 帧打一次日志，避免刷屏
        if self._frame % 60 == 1:
            print(f"[Animator] frame {self._frame:5d} | attr.Set {elapsed:.2f} ms")

    # ----------------------------------------------------------
    # 停止
    # ----------------------------------------------------------
    def stop(self):
        self._stop.set()
        self._sub = None
        self._thread.join(timeout=2.0)
        print("[Animator] 已停止")


# ============================================================
# 5. 主入口
# ============================================================
if __name__ == "__main__":
    pxr_stage = omni.usd.get_context().get_stage()
    stage_id  = omni.usd.get_context().get_stage_id()

    count    = create_point_instancer(pxr_stage, NUM)
    rt_stage = Usd.Stage.Attach(stage_id)
    pos_attr = get_rt_attr(rt_stage)

    # 启动非阻塞动画（主线程立即返回，UI 不卡）
    animator = PointInstancerAnimator(pos_attr, count, amplitude=25.0, speed=2.0)

    print("\n[main] 动画已在后台运行，主线程空闲。")
    print("[main] 停止动画请执行：animator.stop()")
