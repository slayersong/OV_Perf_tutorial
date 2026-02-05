# import omni.usd
import warp as wp
from usdrt import Gf, Rt, Sdf, Usd, UsdGeom
import time
# Load a USD stage and populate Fabric with it
stage_id = omni.usd.get_context().get_stage_id()

stage = Usd.Stage.Attach(stage_id)
for prim in stage.Traverse():
    pass

# Begin example setting world position, select prims
sel = stage.SelectPrims(
    require_attrs=[(Sdf.ValueTypeNames.Matrix4d, "omni:fabric:localMatrix", Usd.Access.ReadWrite)],
    require_prim_type="Mesh",
    device="cuda:0",
)
# End example setting world position, select prims

# Begin example setting world position, kernel
@wp.kernel(enable_backward=False)
def move_prims(xforms: wp.fabricarray(dtype=wp.mat44d)):
    i = wp.tid()
    old_y = xforms[i][3][1]
    # Note: Each [] operator returns by value for differentiability reasons.
    xforms[i] = wp.mat44d(
        wp.vec4d(wp.float64(1.0), wp.float64(0.0), wp.float64(0.0), wp.float64(0.0)),
        wp.vec4d(wp.float64(0.0), wp.float64(1.0), wp.float64(0.0), old_y + wp.float64(19.0)),
        wp.vec4d(wp.float64(0.0), wp.float64(0.0), wp.float64(1.0), wp.float64(0.0)),
        wp.vec4d(wp.float64(0.0), wp.float64(0.0), wp.float64(0.0), wp.float64(1.0)),
    )

# End example setting world position, kernel
print("Running Select with Warp to move the position")
t0 = time.perf_counter()
# Begin example setting world position, apply kernel
with wp.ScopedDevice("cuda:0"):
    xforms = wp.fabricarray(sel, "omni:fabric:localMatrix")
    wp.launch(move_prims, dim=xforms.size, inputs=[xforms], device="cuda:0")
t1 = time.perf_counter()
elapsed_ms = (t1 - t0) * 1000.0

print(f"[USDRT] Select {sel.GetCount()} meshes and move takes {elapsed_ms:.2f} ms")
# End example setting world position, apply kernel

