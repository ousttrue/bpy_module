# bpy_module
build blender as module

## ToDo

* [ ] pyi for bpy

## usage

```
python builder.py {WORKSPACE_FOLDER} {tag} --update --clean --build --install

WORKSPACE_FOLDER
    + blender(git clone)
    + lib(svn checkout)
    + build(cmake build)

tag
    + v2.80
    + v2.81
```

* update: git clone and svn update
* clean: clear WORKSPACE_FOLDER/build 
* build: cmake and msbuild
* install: copy dll and *py to PYTHON_FOLDER/lib/site_lib/blender and PYTHON_FOLDER/2.XX

## requirement

* python interpreter. same version(major.minor) with blender to build 
* vc2019
    * cmake(vc included)
    * msbuild(vc included)
