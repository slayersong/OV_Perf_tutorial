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
    
    def regis(self):
        self._app = omni.kit.app.get_app()          
        self._render_update_sub = self._app.get_update_event_stream().create_subscription_to_pop(
        self.pre_frame_render, order=-10, name="gm_render_event")

    def pre_frame_render(self,e):
        self._pts += 1
        self.get_push_pos_rotate(self._pts)

        if self._pts == 1000:
            begin = time.time()
            carb.log_info(f"before run coroutine")
            run_coroutine(self.await_flush_save())
            #self.flush_save()
            carb.log_info(f"end run coroutine")
            end = time.time()
            carb.log_info(f"elaspe time is {end-begin}")
            self._render_update_sub = None

    def get_push_pos_rotate(self, pts):
        rotae = self._rotation_ops.Get()
        translate = self._translate_ops.Get()

        self._rotate_queue.append(rotae)
        self._translate_queue.append(translate)
        self._pts_queue.append(pts)

    def prepare_data(self):
        begin = time.time()

        rotation_1 = Gf.Vec3f(0.0, 0.0, 0.0)
        _translate = Gf.Vec3d(0.0, 0.0, 0.0)
        for i in range(500):
            # rotation_1 = Gf.Vec3f(0.0, 0.0, 0.0)
            # _translate = Gf.Vec3d(0.0, 0.0, 0.0)
            rotation_1 = Gf.Vec3f(-253.0, i * (360.0 / 499), 93)  # 99是为了最后一次达到360
            # _translate的xyz从0递增到100
            _translate = Gf.Vec3d( 2124.0,  2124.0,  104)

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
                #self._rotation_ops.Set(time = timecode, value = f_val)
                self.seq_write_rotate_op.Set(time = timecode, value = f_val)
            if self._translate_queue:
                d_val = self._translate_queue.popleft()
                self.seq_write_translate_op.Set(time = timecode, value = d_val)
                #self._translate_ops.Set(time = timecode, value = d_val)

            timecode += 10

        self._sub_stage.GetRootLayer().Save()
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

    def create_offline_layer(self, layer_base_path, prim_path, bOverride):
        # split name and ext
        name, ext = os.path.splitext(layer_base_path)

        index = 1
        new_layer_path = layer_base_path

        #If exist create a new path such as basepath_1.usd
        while os.path.exists(new_layer_path):
            new_layer_path = f"{name}_{index}{ext}"
            index += 1

        new_layer = Sdf.Layer.CreateNew(new_layer_path)

        # 2. 打开该layer对应的Stage（编辑该layer）
        self._sub_stage = Usd.Stage.Open(new_layer)

        # 3. 以over方式定义相机Prim（覆盖已有的/world/Camera）
        if bOverride:
            self._seq_camera_prim = self._sub_stage.OverridePrim(prim_path)
            self._seq_camera_prim.SetSpecifier(Sdf.SpecifierOver)
        else:
            self._seq_camera_prim = self._sub_stage.DefinePrim(prim_path)

        # 4. 获取或创建Xformable接口，用于添加变换操作
        xformable = UsdGeom.Xformable(self._seq_camera_prim)

        # 5. 添加translate和rotateXYZ操作
        self.seq_write_translate_op = xformable.AddTranslateOp()
        self.seq_write_rotate_op = xformable.AddRotateXYZOp()
        
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
    
    prim_path = "/World/Camera"
    new_layer_path = "d:\\tes303.usda"

    runclass = TestClass()
    create_prim(_stage, prim_path)
    runclass.init_stage_camera(_stage, prim_path)

    runclass.create_offline_layer(new_layer_path, prim_path, True)
    carb.log_info("create_offline_layer after")

    #runclass.regis()
    runclass.prepare_data()
    begin = time.time()
    carb.log_info(f"before run coroutine")
    run_coroutine(runclass.flush_save_async())
    #run_coroutine(runclass.await_flush_save())
    #runclass.flush_save()
    carb.log_info(f"end run coroutine")
    #runclass.flush_save()
    # with ThreadPoolExecutor() as executor:
    #     executor.submit(runclass.flush_save())

    end = time.time()
    carb.log_info(f"elaspe time is {end-begin} ， 1000 ends")

# class YourClass:
#     def __init__(self):
#         # 初始化队列等
#         pass

#     def flush_save(self):
#         # 这是同步函数，不能改动
#         # 里面调用了Omniverse API，必须在主线程执行
#         print("Begin flush save")
#         time.sleep(1)
#         print("end flush save")

#     async def flush_save_async(self):
#         time0 = time.perf_counter()
#         print("run task begin")
#         loop = asyncio.get_running_loop()
#         # 直接调用同步函数（主线程），但用await asyncio.sleep(0)切分事件循环
#         await loop.run_in_executor(None, self.flush_save)
#         time1 = time.perf_counter()
#         print(f"run task end elaspe:{time1 - time0}")
    
#     async def testawait():
#         pass


# # obj = YourClass()

# # run_coroutine(obj.flush_save_async())
# # print(f"run pass the async")
# # count = 0

# # def pre_frame_render(e):
# #     #print(f"Frame Begin: {app.get_update_number()} {e.payload}, event-type {e.type}, {time.time() * 1000 % 1000000} ")
# #     asyncio.ensure_future(obj.flush_save_async())
# # async def run_task():
# #     time0 = time.perf_counter()
# #     print("run task begin")
# #     await obj.flush_save_async()
# #     print("run task end")
# #     time1 = time.perf_counter()

# #     elapse_time = time1 - time0
# #     print(f"run taks elapse is {elapse_time}")

# # def frame_render(e):
# #     print(f"Frame Render: {app.get_update_number()} {e.payload}, event-type {e.type}, {time.time() * 1000 % 1000000}")

# # def post_frame_render(e):
# #     print(f"Frame End: {app.get_update_number()} {e.payload}, event-type {e.type}, {time.time() * 1000 % 1000000}")

# first_last_event = 1000000

# # pre_update_sub = app.get_pre_update_event_stream().create_subscription_to_pop(
# #     pre_frame_render, order=-first_last_event, name="gm_frame_begin")

# #asyncio.ensure_future(obj.flush_save_async())





