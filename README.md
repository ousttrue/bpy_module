# bpy_module

* Auto clone, build and install blender python module(bpy)
* Link to local python(C:\Python38)
* generate pyi
* Blender v2.83

## require

* vc2019
  * cmake(vc included)
  * msbuild(vc included)
* git https://git-scm.com/
* svn https://sliksvn.com/download/

## usage (build and install bpy)

```sh
python builder.py {WORKSPACE_FOLDER} {tag} --update --clean --build --install --stubs

WORKSPACE_FOLDER
    + blender(git clone)
    + lib(svn checkout)
    + build(cmake build)
```

* update: git clone and svn update
* clean: clear WORKSPACE_FOLDER/build
* build: cmake and msbuild
* install: copy dll and *py to PYTHON_FOLDER/lib/site_lib/blender and PYTHON_FOLDER/2.XX

example

```sh
> C:\Python38\python.exe builder.py --update --build --install C:/bpy_module v2.83
# link to C:\Pyhthon38\libs\python38.lib and install to C:\Python38
```

## generate python stub(pyi)

* Generate pyi stub from installed bpy
* Baseed on https://github.com/mutantbob/pycharm-blender
* Bassed on https://github.com/blender/blender/blob/master/doc/python_api/sphinx_doc_gen.py

```sh
python stub_generator.py
```

example

```sh
> C:\Python38\python.exe stub_generator.py
# generate C:\Python38\lib\site-package\blender\bpy\__init__.pyi
# generate C:\Python38\lib\site-package\blender\mathutils.pyi
```

### use stub on vscode

* install pylance

```json
// settings.json
  "python.languageServer": "Pylance",
  "python.analysis.typeCheckingMode": "basic",
```
