import omni.kit.app
import time
import asyncio
from pxr import Sdf, Usd, UsdGeom, Gf
from omni.kit.usd.layers import LayerUtils, get_layers, LayerEditMode
import omni.kit.commands
from collections import deque
import os
from typing import List, Tuple
from omni.kit.widget.layers.path_utils import PathUtils
import carb
from typing import List, Tuple
from enum import Enum
import asyncio
from pxr import Sdf, Usd, UsdGeom
from pxr import Usd, UsdGeom, Gf
from omni.kit.async_engine import run_coroutine
from concurrent.futures import ALL_COMPLETED, ThreadPoolExecutor, wait

def create_prim(stage, prim_path="/World/Camera"):
    prim = stage.GetPrimAtPath(prim_path)
    if prim and prim.GetTypeName() == "Camera":
        carb.log_info(f"Camera already exists at: {prim_path}")
        return prim
    else:
        camera_prim = UsdGeom.Camera.Define(stage, prim_path)
        camera_prim.AddTranslateOp().Set(Gf.Vec3d(10, 20, 30)) 
        camera_prim.AddRotateXYZOp().Set(Gf.Vec3f(0, 45, 0)) 
        carb.log_info(f"Created new Camera at: {prim_path}")
        return camera_prim.GetPrim()
    
class TestClass:
    def __init__(self):
        self._rotate_queue = deque()
        self._translate_queue = deque()
        self._pts_queue = deque()
        self._pts = 0
        self._Layer_num = 0

    def create_sublayer(self, _root_layer, strLayerName, orderIndex, bSetAuthoring):
        #layname = 
        self._Layer_num += 1
        identifier1 = LayerUtils.create_sublayer(_root_layer, orderIndex, strLayerName).identifier
        #
        if bSetAuthoring:
            omni.kit.commands.execute("SetEditTargetCommand", layer_identifier=identifier1)

    def prepare_data(self):
        begin = time.time()
        rotation_1 = Gf.Vec3f(0.0, 0.0, 0.0)
        _translate = Gf.Vec3d(0.0, 0.0, 0.0)
        for _ in range(10000):
            self._rotate_queue.append(rotation_1)
            self._translate_queue.append(_translate)
        end = time.time()

        carb.log_info(f"prepare_data elaspe:{end - begin}")

    async def await_flush_save(self):
        carb.log_info("before await_flush_save {time.time()}")
        await omni.kit.app.get_app().next_update_async()
        self.flush_save()
        carb.log_info("end await_flush_save {time.time()}")

    def flush_save(self):
        timecode = 0
        while self._rotate_queue or self._translate_queue:
            if self._rotate_queue:
                f_val = self._rotate_queue.popleft()
                self._rotation_ops.Set(time = timecode, value = f_val)
            if self._translate_queue:
                d_val = self._translate_queue.popleft()
                self._translate_ops.Set(time = timecode, value = d_val)

            timecode += 10

        self._render_update_sub = None

    async def awaitflush(self):
        await omni.kit.app.get_app().next_update_async()
        self.flush_save(self)

    async def flush_save_async(self):
        time0 = time.perf_counter()
        carb.log_info("flush_save_async begin")
        loop = asyncio.get_running_loop()
        # 直接调用同步函数（主线程），但用await asyncio.sleep(0)切分事件循环
        await loop.run_in_executor(None, self.flush_save)
        time1 = time.perf_counter()
        carb.log_info(f"flush_save_async end elaspe:{time1 - time0}")

    def init_stage_camera(self, stage, camera_prim_path):
        self._stage = stage
        self._camera_path = camera_prim_path
        self._camera_prim = UsdGeom.Camera.Get(stage, camera_prim_path).GetPrim()
        xform_ops = UsdGeom.Xformable(self._camera_prim).GetOrderedXformOps()

        for op in xform_ops:
                if op.GetOpType() in [UsdGeom.XformOp.TypeRotateXYZ,
                        UsdGeom.XformOp.TypeRotateXZY,
                        UsdGeom.XformOp.TypeRotateYXZ,
                        UsdGeom.XformOp.TypeRotateYZX,
                        UsdGeom.XformOp.TypeRotateZXY,
                        UsdGeom.XformOp.TypeRotateZYX]:
                    #rotation = op.Get()
                    self._rotation_type = op.GetOpType()
                    self._rotation_ops = op
                    #print(f"rotation is {rotation}")
                elif op.GetOpType() == UsdGeom.XformOp.TypeScale:
                    self._scale_ops  = op
                elif op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                    self._translate_ops = op

if __name__ == "__main__":
    _stage = omni.usd.get_context().get_stage()
    root_layer = _stage.GetRootLayer()
    prim_path = "/World/Camera"
    new_layer_path = "d:/camera_sublayer.usd"
    runclass = TestClass()
    
    create_prim(_stage, prim_path)
    runclass.init_stage_camera(_stage, prim_path)
    runclass.create_sublayer(root_layer, new_layer_path,0 ,True)
    runclass.prepare_data()
    
    begin = time.time()
    carb.log_info(f"before run coroutine")
    #(1)Async block UI for about 50 seconds
    run_coroutine(runclass.await_flush_save())
    #(2)Also block UI about 50 seconds
    # with ThreadPoolExecutor() as executor:
    #     executor.submit(runclass.flush_save())
    #(3)Sync, same block
    #self.flush_save()

    end = time.time()
    carb.log_info(f"elaspe time is {end-begin} ， 10000 ends")



