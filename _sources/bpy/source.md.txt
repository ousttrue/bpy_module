# source

<https://github.com/blender/blender>

```
+-------+
|blender|
|+---+  |
||bpy|  |
|+---+  |
+-------+
```
を
```
+---------+
|bpy      |
|+-------+|
||blender||
|+-------+|
+---------+
```
に捻じ曲げるのに初期化がトリッキーになっている。

## entrypoint: PyInit_bpy

python の nativemodule の命名規則により `PyInit_{MODULE_NAME}`。

```py
import bpy
```

でこの関数が呼ばれる。

`source/blender/python/intern/bpy_interface.c`

```c
PyMODINIT_FUNC PyInit_bpy(void)
{
  PyObject *bpy_proxy = PyModule_Create(&bpy_proxy_def);

  // 実際にモジュール(blender全体)を初期化するコールバック
  dealloc_obj_Type.tp_dealloc = dealloc_obj_dealloc;

  // dummy を返す
  return bpy_proxy;
}
```

👇

```c
/* use our own dealloc so we can free a property if we use one */
static void dealloc_obj_dealloc(PyObject *self)
{
  bpy_module_delay_init(((dealloc_obj *)self)->mod);

  /* NOTE: for subclassed PyObjects we can't just call PyObject_DEL() directly or it will crash. */
  dealloc_obj_Type.tp_free(self);
}
```

👇

```c
static void bpy_module_delay_init(PyObject *bpy_proxy)
{
  const int argc = 1;
  const char *argv[2];

  /* updating the module dict below will lose the reference to __file__ */
  PyObject *filename_obj = PyModule_GetFilenameObject(bpy_proxy);

  const char *filename_rel = PyUnicode_AsUTF8(filename_obj); /* can be relative */
  char filename_abs[1024];

  BLI_strncpy(filename_abs, filename_rel, sizeof(filename_abs));
  BLI_path_abs_from_cwd(filename_abs, sizeof(filename_abs));
  Py_DECREF(filename_obj);

  argv[0] = filename_abs;
  argv[1] = NULL;

  // printf("module found %s\n", argv[0]);

  main_python_enter(argc, argv); // 👉 main

  /* initialized in BPy_init_modules() */
  PyDict_Update(PyModule_GetDict(bpy_proxy), PyModule_GetDict(bpy_package_py));
}
```

## main

`source/creator/creator.c`

```c
int main(int argc,
#ifdef WIN32
         const char **UNUSED(argv_c)
#else
         const char **argv
#endif
)
{
  bContext *C;

  WM_init(C, argc, (const char **)argv);
}
```

## WM_init

`source/blender/windowmanager/intern/wm_init_exit.c`

```c
void WM_init(bContext *C, int argc, const char **argv)
{
  BPY_python_start(C, argc, argv);
}
```

## BPY_python_start

`source/blender/python/intern/bpy_interface.c`

```c
/* call BPY_context_set first */
void BPY_python_start(bContext *C, int argc, const char **argv)
{
  /* Defines `bpy.*` and lets us import it. */
  BPy_init_modules(C);
}
```

## BPy_init_modules

`source/blender/python/intern/bpy.c`

```c
/******************************************************************************
 * Description: Creates the bpy module and adds it to sys.modules for importing
 ******************************************************************************/
void BPy_init_modules(struct bContext *C)
{
  PointerRNA ctx_ptr;
  PyObject *mod;

  /* Needs to be first since this dir is needed for future modules */
  const char *const modpath = BKE_appdir_folder_id(BLENDER_SYSTEM_SCRIPTS, "modules");
  if (modpath) {
    // printf("bpy: found module path '%s'.\n", modpath);
    PyObject *sys_path = PySys_GetObject("path"); /* borrow */
    PyObject *py_modpath = PyUnicode_FromString(modpath);
    PyList_Insert(sys_path, 0, py_modpath); /* add first */
    Py_DECREF(py_modpath);
  }
  else {
    printf("bpy: couldn't find 'scripts/modules', blender probably won't start.\n");
  }
  /* stand alone utility modules not related to blender directly */
  IDProp_Init_Types(); /* not actually a submodule, just types */
  IDPropertyUIData_Init_Types();
#ifdef WITH_FREESTYLE
  Freestyle_Init();
#endif

  mod = PyModule_New("_bpy");

  /* add the module so we can import it */
  PyDict_SetItemString(PyImport_GetModuleDict(), "_bpy", mod);
  Py_DECREF(mod);

  /* needs to be first so bpy_types can run */
  PyModule_AddObject(mod, "types", BPY_rna_types());

  /* needs to be first so bpy_types can run */
  BPY_library_load_type_ready();

  BPY_rna_data_context_type_ready();

  BPY_rna_gizmo_module(mod);

  bpy_import_test("bpy_types");
  PyModule_AddObject(mod, "data", BPY_rna_module()); /* imports bpy_types by running this */
  bpy_import_test("bpy_types");
  PyModule_AddObject(mod, "props", BPY_rna_props());
  /* ops is now a python module that does the conversion from SOME_OT_foo -> some.foo */
  PyModule_AddObject(mod, "ops", BPY_operator_module());
  PyModule_AddObject(mod, "app", BPY_app_struct());
  PyModule_AddObject(mod, "_utils_units", BPY_utils_units());
  PyModule_AddObject(mod, "_utils_previews", BPY_utils_previews_module());
  PyModule_AddObject(mod, "msgbus", BPY_msgbus_module());

  RNA_pointer_create(NULL, &RNA_Context, C, &ctx_ptr);
  bpy_context_module = (BPy_StructRNA *)pyrna_struct_CreatePyObject(&ctx_ptr);
  /* odd that this is needed, 1 ref on creation and another for the module
   * but without we get a crash on exit */
  Py_INCREF(bpy_context_module);

  PyModule_AddObject(mod, "context", (PyObject *)bpy_context_module);

  /* Register methods and property get/set for RNA types. */
  BPY_rna_types_extend_capi();

  /* utility func's that have nowhere else to go */
  PyModule_AddObject(mod,
                     meth_bpy_script_paths.ml_name,
                     (PyObject *)PyCFunction_New(&meth_bpy_script_paths, NULL));
  PyModule_AddObject(
      mod, meth_bpy_blend_paths.ml_name, (PyObject *)PyCFunction_New(&meth_bpy_blend_paths, NULL));
  PyModule_AddObject(mod,
                     meth_bpy_user_resource.ml_name,
                     (PyObject *)PyCFunction_New(&meth_bpy_user_resource, NULL));
  PyModule_AddObject(mod,
                     meth_bpy_system_resource.ml_name,
                     (PyObject *)PyCFunction_New(&meth_bpy_system_resource, NULL));
  PyModule_AddObject(mod,
                     meth_bpy_resource_path.ml_name,
                     (PyObject *)PyCFunction_New(&meth_bpy_resource_path, NULL));
  PyModule_AddObject(mod,
                     meth_bpy_escape_identifier.ml_name,
                     (PyObject *)PyCFunction_New(&meth_bpy_escape_identifier, NULL));
  PyModule_AddObject(mod,
                     meth_bpy_unescape_identifier.ml_name,
                     (PyObject *)PyCFunction_New(&meth_bpy_unescape_identifier, NULL));

  /* register funcs (bpy_rna.c) */
  PyModule_AddObject(mod,
                     meth_bpy_register_class.ml_name,
                     (PyObject *)PyCFunction_New(&meth_bpy_register_class, NULL));
  PyModule_AddObject(mod,
                     meth_bpy_unregister_class.ml_name,
                     (PyObject *)PyCFunction_New(&meth_bpy_unregister_class, NULL));

  PyModule_AddObject(mod,
                     meth_bpy_owner_id_get.ml_name,
                     (PyObject *)PyCFunction_New(&meth_bpy_owner_id_get, NULL));
  PyModule_AddObject(mod,
                     meth_bpy_owner_id_set.ml_name,
                     (PyObject *)PyCFunction_New(&meth_bpy_owner_id_set, NULL));


  /* add our own modules dir, this is a python package */
  bpy_package_py = bpy_import_test("bpy");
}
```

