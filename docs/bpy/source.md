# source

bpy module のソース。

## PyInit_bpy

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


`source/blender/python/intern/bpy_interface.c`

```c
PyMODINIT_FUNC PyInit_bpy(void)
{
  PyObject *bpy_proxy = PyModule_Create(&bpy_proxy_def);
}
```

`main_python_enter` => `main`

`source/blender/python/intern/bpy.c`

```c
void BPy_init_modules(struct bContext *C)
{
    // import 時の初期化処理
}
```

