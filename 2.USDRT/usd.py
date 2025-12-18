from pxr import Gf, Sdf, Usd, UsdGeom, Vt
import omni
import time
import carb

stage = omni.usd.get_context().get_stage()
color = Vt.Vec3fArray([Gf.Vec3f(0.8, 0.2,0 )])
# 遍历所有 prim，筛选出 Mesh
mesh_prims = []
for prim in stage.Traverse():
    if prim.IsA(UsdGeom.Mesh):
        mesh_prims.append(prim)

t0 = time.perf_counter()

for prim in mesh_prims:
    if prim.HasAttribute(UsdGeom.Tokens.primvarsDisplayColor):
        #carb.log_info(f"The prim is {prim}")
        prim.GetAttribute(UsdGeom.Tokens.primvarsDisplayColor).Set(color)

t1 = time.perf_counter()
elapsed_ms = (t1 - t0) * 1000.0

carb.log_warn(f"[Native USD] Painted {len(mesh_prims)} meshes in {elapsed_ms:.2f} ms")







