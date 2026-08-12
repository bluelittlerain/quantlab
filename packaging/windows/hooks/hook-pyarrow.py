from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

# PyArrow's upstream hook includes C++ headers and test fixture files. QuantLab
# needs the runtime modules and DLLs only.
hiddenimports = collect_submodules("pyarrow", filter=lambda name: ".tests" not in name)
binaries = collect_dynamic_libs("pyarrow")
datas = []
