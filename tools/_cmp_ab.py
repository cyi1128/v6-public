import py_compile
for p in [r"services\control_profile.py", r"ui\battle_widgets\base.py"]:
    py_compile.compile(p, doraise=True)
print("编译通过")
