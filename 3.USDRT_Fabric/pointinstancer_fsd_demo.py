"""PointInstancer + FSD + Warp in-place demo.

Pipeline (no base/out scratch, no Vt copy — kernel mutates Fabric directly):

    @wp.kernel on cuda
         │  reads + writes positions via wp.fabricarrayarray(sel, "positions")
         ▼
    Fabric (in place)
         │
    FSD (on by default)
         │
    Hydra + RTX viewport
         │
    capture_viewport_to_file             # PNG at /kit-demos/out/

Launch:
  ~/git/kit/kit/_build/linux-x86_64/release/omni.app.dev.rtx.sh \
      --enable usdrt.scenegraph \
      --enable omni.warp \
      --no-window \
      --/persistent/app/file/ignoreUnsavedOnExit=true \
      --/app/file/ignoreUnsavedStage=true \
      --/app/fastShutdown=true \
      --exec "/home/horde/git/runtime-poc-april/kit-demos/pointinstancer_fsd_demo.py"

Note: PointInstancer prim + prototype relationship + initial positions are
authored once via pxr (that's the only way — Fabric is a runtime cache, prims
have to exist on the USD stage before Fabric picks them up). Every per-frame
position update goes through Fabric.
"""

import asyncio
import math
import os

import numpy as np

import carb
import omni.kit.app
import omni.usd

from omni.kit.viewport.utility import (
    get_active_viewport,
    capture_viewport_to_file,
)

OUT_DIR = "/home/horde/git/runtime-poc-april/kit-demos/out"
N_SIDE = 316
N = N_SIDE * N_SIDE  # 99 856 instances ≈ 100 000
SPACING = 0.5
AMPLITUDE = 4.0
WARMUP_FRAMES = 120     # let RTX compile shaders + load the scene
FRAMES_BETWEEN_CAPS = 60
CAPTURE_PHASES = 3


def _log(msg):
    carb.log_warn(f"[pi-demo] {msg}")
    print(f"[pi-demo] {msg}", flush=True)


async def _main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # ---------------------------------------------- one-time stage authoring
    from pxr import UsdGeom, UsdLux, Gf, Vt

    ctx = omni.usd.get_context()
    await ctx.new_stage_async()
    stage = ctx.get_stage()

    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.Xform.Define(stage, "/World")

    UsdGeom.Cube.Define(stage, "/World/Proto/Cube").CreateSizeAttr(1.0)

    pi = UsdGeom.PointInstancer.Define(stage, "/World/Instancer")
    pi.CreatePrototypesRel().AddTarget("/World/Proto/Cube")

    base = np.zeros((N, 3), dtype=np.float32)
    for i in range(N):
        ix, iy = i % N_SIDE, i // N_SIDE
        base[i, 0] = (ix - N_SIDE / 2) * SPACING
        base[i, 1] = (iy - N_SIDE / 2) * SPACING

    pi.CreateProtoIndicesAttr([0] * N)
    pi.CreatePositionsAttr(Vt.Vec3fArray(
        [Gf.Vec3f(float(p[0]), float(p[1]), float(p[2])) for p in base]
    ))
    pi.CreateScalesAttr([Gf.Vec3f(0.35, 0.35, 0.35)] * N)
    pi.CreateOrientationsAttr([Gf.Quath(1, 0, 0, 0)] * N)

    cam = UsdGeom.Camera.Define(stage, "/World/Camera")
    cam_xf = UsdGeom.Xformable(cam)
    # Camera pulled back so the whole grid fits in frame regardless of N.
    grid_extent = N_SIDE * SPACING
    cam_xf.AddTranslateOp().Set(Gf.Vec3d(0, -grid_extent * 1.2, grid_extent * 0.6))
    cam_xf.AddRotateXYZOp().Set(Gf.Vec3f(60, 0, 0))

    light = UsdLux.DistantLight.Define(stage, "/World/Light")
    light.CreateIntensityAttr(3000.0)
    UsdGeom.Xformable(light).AddRotateXYZOp().Set(Gf.Vec3f(-45, 30, 0))

    plane = UsdGeom.Mesh.Define(stage, "/World/Ground")
    size = N_SIDE * SPACING * 0.7
    plane.CreatePointsAttr([
        Gf.Vec3f(-size, -size, -0.6),
        Gf.Vec3f( size, -size, -0.6),
        Gf.Vec3f( size,  size, -0.6),
        Gf.Vec3f(-size,  size, -0.6),
    ])
    plane.CreateFaceVertexCountsAttr([4])
    plane.CreateFaceVertexIndicesAttr([0, 1, 2, 3])

    _log(f"authored {N} instances")

    vp = get_active_viewport()
    vp.camera_path = "/World/Camera"

    app = omni.kit.app.get_app()
    _log(f"warming up for {WARMUP_FRAMES} frames...")
    for _ in range(WARMUP_FRAMES):
        await app.next_update_async()

    # --------------------------------------- usdrt / Fabric selection (required)
    # PointInstancer.positions is schema-typed Vec3fArray with role "Point",
    # which in usdrt's Sdf.ValueTypeNames is Point3fArray (NOT Vector3fArray —
    # that role is for velocities/directions).
    import usdrt
    from usdrt import Sdf as RtSdf
    rt_stage = usdrt.Usd.Stage.Attach(ctx.get_stage_id())
    sel = rt_stage.SelectPrims(
        require_attrs=[(
            RtSdf.ValueTypeNames.Point3fArray,
            "positions",
            usdrt.Usd.Access.ReadWrite,
        )],
        require_prim_type="PointInstancer",
        device="cuda:0",
    )
    assert sel.GetCount() == 1, f"expected 1 PointInstancer, got {sel.GetCount()}"
    _log(f"Fabric selection: {sel.GetCount()} PointInstancer prim(s)")

    # ----------------------------------------------- Warp on GPU (required)
    import warp as wp
    wp.init()
    assert wp.is_cuda_available(), "CUDA-capable Warp is required"

    with wp.ScopedDevice("cuda:0"):
        positions_fabric = wp.fabricarrayarray(data=sel, attrib="positions")

    @wp.kernel
    def sine_wave_inplace(
        positions: wp.fabricarrayarray(dtype=wp.vec3f),
        phase: float,
        amplitude: float,
    ):
        i = wp.tid()
        p = positions[0, i]                          # [prim_idx, instance_idx]
        z = amplitude * wp.sin(phase + 0.25 * (p[0] + p[1]))
        positions[0, i] = wp.vec3f(p[0], p[1], z)

    _log("Warp ready on cuda; fabricarrayarray bound to Fabric in place")

    # ---------------------------------------------------------- animation loop
    for i in range(CAPTURE_PHASES):
        phase = i * (2.0 * math.pi / 3.0)
        _log(f"phase {i}: {phase:.3f} rad")

        wp.launch(
            sine_wave_inplace,
            dim=N,
            inputs=[positions_fabric, float(phase), float(AMPLITUDE)],
            device="cuda:0",
        )
        wp.synchronize()

        for _ in range(FRAMES_BETWEEN_CAPS):
            await app.next_update_async()

        out = os.path.join(OUT_DIR, f"phase_{i}.png")
        capture_viewport_to_file(vp, file_path=out)
        _log(f"  capture -> {out}")
        for _ in range(20):
            await app.next_update_async()

    for _ in range(30):
        await app.next_update_async()

    _log("done")
    omni.kit.app.get_app().post_quit()


async def _safety_quit():
    await asyncio.sleep(120)
    _log("safety_quit: 120 s elapsed, forcing exit")
    omni.kit.app.get_app().post_quit()


def _wrap():
    async def runner():
        try:
            await _main()
        except Exception as e:
            import traceback
            _log(f"_main EXCEPTION: {e}")
            _log(traceback.format_exc())
            omni.kit.app.get_app().post_quit()

    asyncio.ensure_future(runner())
    asyncio.ensure_future(_safety_quit())


_wrap()
