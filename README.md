# bpy_module

build blender as module

## require
### build
* vc2019
  * cmake(vc included)
  * msbuild(vc included)
* git https://git-scm.com/
* svn https://sliksvn.com/download/

### runtime
* numpy

## usage

```
python builder.py {WORKSPACE_FOLDER} {tag} --update --clean --build --install --stubs

WORKSPACE_FOLDER
    + blender(git clone)
    + lib(svn checkout)
    + build(cmake build)

tag
    + v2.83
```

* update: git clone and svn update
* clean: clear WORKSPACE_FOLDER/build
* build: cmake and msbuild
* install: copy dll and *py to PYTHON_FOLDER/lib/site_lib/blender and PYTHON_FOLDER/2.XX
* stub: generate pyi file. use pyright with vscode.
