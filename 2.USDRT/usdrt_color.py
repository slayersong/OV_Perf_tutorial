from usdrt import Gf, Sdf, Usd, UsdGeom, Vt

stage = Usd.Stage.Attach(omni.usd.get_context().get_stage_id())

path = "/Cornell_Box/Root/Cornell_Box1_LP/White_Wall_Back"
prim = stage.GetPrimAtPath(path)
attr = prim.GetAttribute(UsdGeom.Tokens.primvarsDisplayColor)
# Get the value of displayColor on White_Wall_Back,
# which is mid-gray on this stage
result = attr.Get()
print(f"before set color is {result}")
attr.Set(Vt.Vec3fArray([Gf.Vec3f(1, 0, 0)]))
result = attr.Get()
print(f"after set color is {result}")
