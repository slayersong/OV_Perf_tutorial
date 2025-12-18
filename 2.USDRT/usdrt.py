from usdrt import Gf, Sdf, Usd, UsdGeom, Vt
import omni
import time
import usdrt
stage = usdrt.Usd.Stage.Attach(omni.usd.get_context().get_stage_id())

from usdrt import Gf, Sdf, Usd, UsdGeom, Vt
import carb
color = Vt.Vec3fArray([Gf.Vec3f(0.2, 0.2,0)])
meshPaths = stage.GetPrimsWithTypeName("Mesh")
t0 = time.perf_counter()
for meshPath in meshPaths:
    prim = stage.GetPrimAtPath(meshPath)
    if prim.HasAttribute(UsdGeom.Tokens.primvarsDisplayColor):
        #carb.log_info(f"The prim is {prim}")
        prim.GetAttribute(UsdGeom.Tokens.primvarsDisplayColor).Set(color)
t1 = time.perf_counter()
elapsed_ms = (t1 - t0) * 1000.0

carb.log_warn(f"[USDRT] Painted {len(meshPaths)} meshes in {elapsed_ms:.2f} ms")








