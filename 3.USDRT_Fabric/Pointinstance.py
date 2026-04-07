"""
Omniverse / Isaac Sim：创建 PointInstancer + 按索引操作单个 instance
在 Script Editor 中运行（需已有 Stage）。
"""
from pxr import Usd, UsdGeom, Sdf, Gf
import omni.usd
import random


def get_stage():
    return omni.usd.get_context().get_stage()


# ========== 1. 创建 PointInstancer（与之前「最基础」写法一致）==========
def create_point_instancer(stage, num_instances):
    root_path = "/World"
    instancer_path = root_path + "/MyPointInstancer"
    prototype_path = instancer_path + "/Prototype_Box"

    # 单位：厘米（Omniverse 默认），Cube 边长 50 cm，网格间距 100 cm
    CUBE_SIZE   = 50.0   # Prototype cube 边长（cm）
    GRID_STEP   = 100.0  # 网格格距（cm）
    RAND_XZ     = 20.0   # XZ 方向随机偏移幅度（cm）
    RAND_Y_MAX  = 30.0   # Y 方向随机抬起最大值（cm）

    UsdGeom.Xform.Define(stage, root_path)

    cube = UsdGeom.Cube.Define(stage, prototype_path)
    cube.CreateSizeAttr(CUBE_SIZE)
    cube.CreateDisplayColorAttr().Set([Gf.Vec3f(0.2, 0.6, 1.0)])

    instancer = UsdGeom.PointInstancer.Define(stage, instancer_path)
    instancer.GetPrototypesRel().AddTarget(Sdf.Path(prototype_path))

    proto_indices = []
    positions = []
    orientations = []
    scales = []

    for i in range(num_instances):
        for j in range(num_instances):
            proto_indices.append(0)
            # 每个 instance 在网格基础上叠加独立随机偏移
            rx = random.uniform(-RAND_XZ, RAND_XZ)
            ry = random.uniform(0.0, RAND_Y_MAX)
            rz = random.uniform(-RAND_XZ, RAND_XZ)
            positions.append(Gf.Vec3f(
                i * GRID_STEP + rx,
                ry,
                j * GRID_STEP + rz,
            ))
            orientations.append(Gf.Quath(1.0, 0.0, 0.0, 0.0))
            scales.append(Gf.Vec3f(1.0, 1.0, 1.0))

    instancer.GetProtoIndicesAttr().Set(proto_indices)
    instancer.GetPositionsAttr().Set(positions)
    instancer.GetOrientationsAttr().Set(orientations)
    instancer.GetScalesAttr().Set(scales)

    return instancer, len(proto_indices)


# ========== 2. 按索引操作「单个」instance（改数组里第 index 项）==========
def set_instance_position(instancer: UsdGeom.PointInstancer, index: int, pos: Gf.Vec3f):
    attr = instancer.GetPositionsAttr()
    positions = list(attr.Get())
    if index < 0 or index >= len(positions):
        raise IndexError(f"instance index {index} out of range [0, {len(positions)})")
    positions[index] = pos
    attr.Set(positions)


def set_instance_orientation(instancer: UsdGeom.PointInstancer, index: int, quat: Gf.Quath):
    attr = instancer.GetOrientationsAttr()
    orientations = list(attr.Get())
    if index < 0 or index >= len(orientations):
        raise IndexError(f"instance index {index} out of range")
    orientations[index] = quat
    attr.Set(orientations)


def set_instance_scale(instancer: UsdGeom.PointInstancer, index: int, scale: Gf.Vec3f):
    attr = instancer.GetScalesAttr()
    scales = list(attr.Get())
    if index < 0 or index >= len(scales):
        raise IndexError(f"instance index {index} out of range")
    scales[index] = scale
    attr.Set(scales)


def get_instance_transform(instancer: UsdGeom.PointInstancer, index: int):
    """读出第 index 个实例的 position / orientation / scale（若存在）。"""
    positions = instancer.GetPositionsAttr().Get()
    orientations = instancer.GetOrientationsAttr().Get()
    scales_attr = instancer.GetScalesAttr()
    scales = scales_attr.Get() if scales_attr.HasAuthoredValue() else None
    return {
        "position": positions[index],
        "orientation": orientations[index],
        "scale": scales[index] if scales else None,
    }


# ========== 3. 运行示例 ==========
if __name__ == "__main__":
    stage = get_stage()
    instancer_prim, count = create_point_instancer(stage, 10)
    instancer = UsdGeom.PointInstancer(instancer_prim.GetPrim())

    # 把「第 4 个」instance（索引 3）额外抬起并放大、绕 Y 转一点
    k = 3
    set_instance_position(instancer, k, Gf.Vec3f(100.0, 75.0, 100.0))
    set_instance_scale(instancer, k, Gf.Vec3f(1.5, 1.5, 1.5))
    # 绕 Y 轴约 45°：Quath(w, x, y, z)，单位四元数
    import math
    half = math.radians(45.0) * 0.5
    set_instance_orientation(
        instancer,
        k,
        Gf.Quath(math.cos(half), 0.0, math.sin(half), 0.0),
    )

    print("instance count:", count)
    print("instance[3]:", get_instance_transform(instancer, 3))