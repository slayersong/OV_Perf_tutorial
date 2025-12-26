from usdrt import Gf, Rt, Sdf, Usd
import carb.events
import omni.usd
import omni.kit.app
import asyncio


class RTTrackingTester:
    def __init__(self):
        ctx = omni.usd.get_context()
        self._stage = Usd.Stage.Attach(ctx.get_stage_id())

        self._light_prim = self._stage.GetPrimAtPath(Sdf.Path("/DistantLight"))
        self._cube_prim = self._stage.GetPrimAtPath(Sdf.Path("/Cube_5"))
        self._sphere_prim = self._stage.GetPrimAtPath(Sdf.Path("/Sphere_2"))

        self._tracker = Rt.ChangeTracker(self._stage)
        self._tracker.TrackAttribute("inputs:color")
        self._tracker.TrackAttribute("visibility")
        self._tracker.TrackAttribute("subdivisionScheme")

        # 全局 update 计数
        self._update_counter = 0

        # 是否已经发现过变化
        self._changed_seen = False
        # 第一次发现变化时的 update 计数
        self._first_change_update_index = -1
        # 从第一次变化起，已经经历的 on_update 次数
        self._updates_since_first_change = 0
        # 5 次以后 ClearChanges 并退出
        self._updates_after_change_to_clear = 5

        update_stream = omni.kit.app.get_app().get_update_event_stream()
        self._subscription = update_stream.create_subscription_to_pop(
            self.on_update,
            name="RTTrackingTester_Update_Subscription"
        )

        print("[RTTrackingTester] Initialized")

    def _get_changed_attrs_for_prim(self, prim):
        if not prim or not prim.IsValid():
            return []
        return self._tracker.GetChangedAttributes(prim)

    def _check_and_print_changes(self):
        """检查是否有 tracked attribute 变化，只在有变化时打印"""
        changed_any = False

        for prim in (self._light_prim, self._cube_prim, self._sphere_prim):
            changed = self._get_changed_attrs_for_prim(prim)
            if changed:
                changed_any = True
                print(f"[RTTrackingTester] Changed attributes on {prim.GetPath()}:")
                for attr in changed:
                    # usdrt Rt.Attribute 通常有 GetName()
                    try:
                        name = attr.GetName()
                    except AttributeError:
                        name = str(attr)
                    print(f"  - {name}")

        return changed_any

    def on_update(self, e: carb.events.IEvent):
        self._update_counter += 1

        # 每次 update 都检查一次变化（如果你想降频，可以加模运算）
        changed_any = self._check_and_print_changes()

        # 第一次发现变化
        if changed_any and not self._changed_seen:
            self._changed_seen = True
            self._first_change_update_index = self._update_counter
            self._updates_since_first_change = 0
            print(f"[RTTrackingTester] First change detected at update #{self._update_counter}")

        # 如果已经发现过变化，统计从那之后经历了多少次 on_update
        if self._changed_seen:
            self._updates_since_first_change += 1

            # 达到指定次数后 ClearChanges 并退出
            if self._updates_since_first_change >= self._updates_after_change_to_clear:
                # ClearChanges/Reset 二选一
                if hasattr(self._tracker, "ClearChanges"):
                    self._tracker.ClearChanges()
                    print("[RTTrackingTester] ClearChanges() called after "
                          f"{self._updates_since_first_change} updates since first change")
                else:
                    self._tracker.Reset()
                    print("[RTTrackingTester] Reset() called after "
                          f"{self._updates_since_first_change} updates since first change")

                self.shutdown()

    def shutdown(self):
        if self._subscription:
            self._subscription = None
        print("[RTTrackingTester] shutdown, on_update will no longer be called")


async def _change_light_color_after_delay(stage, delay_sec: float = 1.0):
    """异步等待一段时间后，主动修改 /DistantLight.inputs:color"""
    await asyncio.sleep(delay_sec)

    light_prim = stage.GetPrimAtPath(Sdf.Path("/DistantLight"))
    if not light_prim or not light_prim.IsValid():
        print("[RTTrackingTester] /DistantLight prim invalid, cannot change color")
        return

    light_color_attr = light_prim.GetAttribute("inputs:color")
    if not light_color_attr:
        print("[RTTrackingTester] /DistantLight has no 'inputs:color' attribute")
        return

    new_color = Gf.Vec3f(0.2, 0.3, 0.4)
    light_color_attr.Set(new_color, Usd.TimeCode(0.0))
    print(f"[RTTrackingTester] Changed /DistantLight.inputs:color to {new_color}")


if __name__ == "__main__":
    ctx = omni.usd.get_context()
    stage = Usd.Stage.Attach(ctx.get_stage_id())

    tester = RTTrackingTester()
    print("[RTTrackingTester] Script running, will change light color after 1 second...")

    loop = asyncio.get_event_loop()
    loop.create_task(_change_light_color_after_delay(stage, 1.0))
