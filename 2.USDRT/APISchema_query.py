from pxr import Usd, Tf
schema_reg = Usd.SchemaRegistry()
single_apply_list = []
multiple_apply_list = []
for t in Tf.Type.FindByName("UsdAPISchemaBase").GetAllDerivedTypes():
    if not (schema_reg.IsAppliedAPISchema(t) or schema_reg.IsMultipleApplyAPISchema(t)):        
        continue
    
    if (schema_reg.IsAppliedAPISchema(t) and not schema_reg.IsMultipleApplyAPISchema(t)):
        single_apply_list.append(str(t).split("'")[1::2][0])
        
    if (schema_reg.IsMultipleApplyAPISchema(t)):
        multiple_apply_list.append(str(t).split("'")[1::2][0])
        

# Sort and print
print("Single-apply API Schemas:")
for x in sorted(single_apply_list):
    print(x)
print("\nMulti-apply API Schemas:")
for x in sorted(multiple_apply_list):
    print(x)
