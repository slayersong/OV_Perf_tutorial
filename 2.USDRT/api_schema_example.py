from usdrt import Gf, Sdf, Usd, UsdGeom, Vt
import usdrt
import carb

stage = usdrt.Usd.Stage.Attach(omni.usd.get_context().get_stage_id())

color = Vt.Vec3fArray([Gf.Vec3f(0.2, 0.2,0)])
meshPaths = stage.GetPrimsWithTypeName("Mesh")
for meshPath in meshPaths:
    prim = stage.GetPrimAtPath(meshPath)
    print(f"Mesh prim is {prim}")
    
shapingPaths = stage.GetPrimsWithAppliedAPIName("ShapingAPI")
for shapingPath in shapingPaths:
    prim = stage.GetPrimAtPath(shapingPath)
    print(f"shaping prim is {prim}")
    
collect_lighting_paths = stage.GetPrimsWithAppliedAPIName("CollectionAPI:lightLink")
for collect_lighting_path in collect_lighting_paths:
    prim = stage.GetPrimAtPath(collect_lighting_path)
    print(f"collect_lighting_path prim is {prim}")
