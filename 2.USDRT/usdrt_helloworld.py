import usdrt

stage = usdrt.Usd.Stage.Attach(omni.usd.get_context().get_stage_id())

print(f"USD RT Hello world, USDRT Stage {stage}")


