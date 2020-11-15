from inspect import isclass, ismodule
import io
from io import TextIOWrapper
from re import split
import types
import inspect
import pathlib
import sys
import re
from typing import Collection, DefaultDict, List, Dict, NamedTuple, Optional, Any

import bpy
import bpy_extras.io_utils
import bpy_extras.image_utils
import mathutils
# these two strange lines below are just to make the debugging easier (to let it run many times from within Blender)
import imp
import rna_info
imp.reload(
    rna_info
)  # to avoid repeated arguments in function definitions on second and the next runs - a bug in rna_info.py....

HERE = pathlib.Path(__file__).parent
PY_DIR = pathlib.Path(sys.executable).parent
BL_DIR = PY_DIR / 'Lib/site-packages/blender'


class PythonType:
    def __init__(self, name: str):
        self.name = name

    def __str__(self) -> str:
        # quoted
        return f"'{self.name}'"


class BuiltinType(PythonType):
    def __init__(self, name: str):
        super().__init__(name)

    def __str__(self) -> str:
        return f"{self.name}"


class PropCollectionType(PythonType):
    def __init__(self, item_type: PythonType):
        super().__init__(f"bpy_prop_collection[{item_type}]")
        self.item_type = item_type

    def __str__(self) -> str:
        return f"'bpy_prop_collection[{self.item_type.name}]'"


class NoType(PythonType):
    def __init__(self):
        super().__init__('')


class AnyType(PythonType):
    def __init__(self):
        super().__init__('Any')


class UnionType(PythonType):
    def __init__(self, *args):
        super().__init__('Union')
        self.types = args

    def __str__(self) -> str:
        types = ', '.join([str(t) for t in self.types])
        return f"'Union[{types}]'"


class PythonTypeFactory:
    def __init__(self):
        STR = BuiltinType('str')
        BOOL = BuiltinType('bool')
        INT = BuiltinType('int')
        FLOAT = BuiltinType('float')
        DATETIME = BuiltinType('datetime.timedelta')
        self.python_type_map: Dict[str, PythonType] = {
            'str':
            STR,
            'string':
            STR,
            'boolean':
            BOOL,
            'bool':
            BOOL,
            'int':
            INT,
            'float':
            FLOAT,
            'int or float.':
            UnionType(INT, FLOAT),
            'int, float or ``datetime.timedelta``.':
            UnionType(INT, FLOAT, DATETIME),
            'datetime.timedelta':
            DATETIME,
            'number or a ``datetime.timedelta`` object':
            UnionType(FLOAT, DATETIME)
        }
        # #
        # 'function':
        # 'Callable[[], None]',
        # 'sequence':
        # 'List[Any]',
        # 'class':
        # 'type',
        # 'sequence of string tuples or a function':
        # 'List[str]',
        # 'string or set':
        # 'str',
        # 'type':
        # 'type',
        # #
        # 'set':
        # 'set',
        # 'list':
        # 'list',
        # #
        # 'sequence of numbers':
        # 'Sequence[float]',
        # '2d number sequence':
        # 'Sequence[Tuple[float, float]]',
        # 'float triplet':
        # 'Tuple[float, float, float]',
        # '3d vector':
        # 'Tuple[float, float, float]',
        # 'Vector':
        # 'Vector',
        # ':class:`Vector`':
        # 'Vector',
        # 'Matrix Access':
        # 'Matrix',
        # ':class:`Matrix`':
        # 'Matrix',
        # ':class:`Quaternion`':
        # 'Quaternion',
        # '(:class:`Vector`, :class:`Quaternion`, :class:`Vector`)':
        # 'Tuple[Vector, Quaternion, Vector]',
        # ':class:`Euler`':
        # 'Euler',
        # '(:class:`Vector`, float) pair':
        # 'Tuple[Vector, float]',
        # '(:class:`Quaternion`, float) pair':
        # 'Tuple[Quaternion, float]',
        # 'tuple':
        # 'List[float]',
        # 'tuple of strings':
        # 'List[str]',
        # 'list of strings':
        # 'List[str]',
        # 'collection of strings or None.':
        # 'List[str]',
        # 'generator':
        # 'List[Any]',
        # 'tuple pair of functions':
        # 'Any',
        # ':class:`bpy.types.WorkSpaceTool` subclass.':
        # 'bpy.types.WorkSpaceTool',
        # }
        self.enum_map = {}
        self.any_type = AnyType()
        self.no_type = NoType()
        self.str_type = PythonType('str')

    def from_name(self, src: str) -> PythonType:
        pt = self.python_type_map.get(src)
        if pt:
            return pt

        if not src:
            return self.any_type

        if src == 'any':
            return self.any_type

        if src.startswith('string in '):
            # ToDo: ENUM
            return self.from_name('str')

        pt = self.python_type_map.get(src)
        if pt is not None:
            return pt

        pt = PythonType(src)
        print(src)
        self.python_type_map[src] = pt
        return pt

        # if value_type == 'Any':
        #     print(src)
        # if array_length == 0:
        #     return value_type

        # if value_type == 'float':
        #     if array_length == 9:
        #         return 'Matrix'
        #     if array_length == 16:
        #         return 'Matrix'
        #     return 'Vector'

        # values = ', '.join([value_type] * array_length)
        # return f'Tuple[{values}]'

        pt = PythonType(name)
        self.python_type_map[name] = pt
        return pt

    def from_prop(self, prop) -> PythonType:
        if prop.type == 'collection':
            if prop.srna:
                return self.from_name(prop.srna.identifier)
            else:
                item_type = self.from_name(prop.fixed_type.identifier)
                pt = PropCollectionType(item_type)
                if pt.name in self.python_type_map:
                    return self.python_type_map[pt.name]

                self.python_type_map[pt.name] = pt
                return pt

        if prop.type == 'enum':
            key = f'Enum{prop.identifier[0].upper()}{prop.identifier[1:]}'
            self.enum_map[key] = prop.enum_items
            return self.from_name('str')  #key

        if prop.type == 'pointer':
            return self.from_name(prop.fixed_type.identifier)

        return self.from_name(prop.type)


FACTORY = PythonTypeFactory()


class StubProperty(NamedTuple):
    name: str
    type: PythonType
    default: Any = None

    @staticmethod
    def from_rna(prop) -> 'StubProperty':
        return StubProperty(prop.identifier, FACTORY.from_prop(prop),
                            prop.default_str)

    def __str__(self) -> str:
        if self.default is None:
            return f'{self.name}: {self.type}'
        else:
            return f'{self.name}: {self.type} = {self.default}'


def format_function(name: str, is_method: bool, params: List[StubProperty],
                    ret_types: List[PythonType]) -> str:
    indent = '    ' if is_method else ''
    str_ret_types = [str(r) for r in ret_types]
    str_params = [str(p) for p in params]
    if is_method:
        str_params = ['self'] + str_params

    if not ret_types:
        return f'{indent}def {name}({", ".join(str_params)}) -> None: ... # noqa'
    elif len(ret_types) == 1:
        return f'{indent}def {name}({", ".join(str_params)}) -> {str_ret_types[0]}: ... # noqa'
    else:
        return f'{indent}def {name}({", ".join(str_params)}) -> Tuple[{", ".join(str_ret_types)}]: ... # noqa'


class StubFunction(NamedTuple):
    name: str
    ret_types: List[PythonType]
    params: List[StubProperty]
    is_method: bool

    def __str__(self) -> str:
        return format_function(self.name, self.is_method, self.params,
                               self.ret_types)

    @staticmethod
    def from_rna(func, is_method: bool) -> 'StubFunction':
        ret_values = [FACTORY.from_prop(v) for v in func.return_values]
        args = [StubProperty.from_rna(a) for a in func.args]
        return StubFunction(func.identifier, ret_values, args, is_method)


class StubStruct:
    def __init__(self, name: str, base: Optional[PythonType],
                 properties: List[StubProperty], methods: List[StubFunction],
                 refs: List[str]):
        self.name: str = name
        self.base: Optional[PythonType] = base
        self.properties: List[StubProperty] = properties
        self.methods: List[StubFunction] = methods
        self.refs = refs

    def set_prop_type(self, prop_name: str, prop_type: PythonType):
        for i, prop in enumerate(self.properties):
            if prop.name == prop_name:
                self.properties[i] = StubProperty(prop.name, prop_type)
                print(f'{self.name}.{prop.name} = {prop_type}')
                return

    def to_str(self, types: List['StubStruct']) -> str:
        sio = io.StringIO()
        sio.write(f'class {self.name}')
        if self.base:
            base_name = str(self.base).replace("'", '')
            sio.write(f'({base_name})')
        sio.write(':\n')

        for prop in self.properties:
            if self.name == 'RenderEngine' and prop.name == 'render':
                # skip
                continue
            sio.write(f'    {prop.name}: {prop.type}\n')

        for func in self.methods:
            sio.write(f'{func}\n')

        # if self.name == 'Object':
        #     # hard coding
        #     sio.write(f"    children: bpy_prop_collection['Object']\n")

        if not self.properties and not self.methods:
            sio.write('    pass\n')

        return sio.getvalue()

    def enable_base(self, used: List[PythonType]) -> bool:
        if not self.base:
            return True

        if self.base.name == self.name:
            return True

        for u in used:
            if self.base == u:
                return True
            if isinstance(self.base,
                          PropCollectionType) and self.base.item_type == u:
                return True

        return False

    @staticmethod
    def from_rna(s) -> 'StubStruct':
        base: Optional[PythonType] = None
        if s.base:
            base = FACTORY.from_name(s.base.identifier)
        elif s.description.startswith('Collection of '):
            splited = s.description.split(' ', 2)
            # item = FACTORY.from_name(s.identifier[0:-1])
            if s.functions and s.functions[0].return_values:
                item_type = s.functions[0].return_values[
                    0].fixed_type.full_path
                item = FACTORY.from_name(item_type)
                base = PropCollectionType(item)

        if s.identifier == 'Object':
            print(s)
        stub = StubStruct(
            s.identifier, base,
            [StubProperty.from_rna(prop) for prop in s.properties],
            [StubFunction.from_rna(func, True)
             for func in s.functions], s.references[:]
            if s.description.startswith('Collection of ') else [])
        if s.identifier == 'UVLoopLayers':
            print(s)
        return stub


def escape_enum_name(src: str) -> str:
    return src.replace(' ', '').replace('-', '')


class StubModule:
    def __init__(self, name: str) -> None:
        self.name = name
        self.types: List[StubStruct] = []

    def __str__(self) -> str:
        return f'{self.name}({len(self.types)}types)'

    def push(self, _s) -> None:
        if _s.identifier == 'PropertyGroupItem':
            # skip
            return
        self.types.append(StubStruct.from_rna(_s))

    def enumerate(self):
        types = self.types[:]
        used = []

        while len(types):
            remove = []
            for t in types:
                if t.enable_base(used):
                    remove.append(t)
                    yield t
            if len(remove) == 0:
                raise Exception('Error')
            used += [FACTORY.from_name(r.name) for r in remove]
            for r in remove:
                types.remove(r)

    def generate(self, dir: pathlib.Path, prev: str, additional: List[str]):
        bpy_types_pyi: pathlib.Path = dir / self.name.replace(
            '.', '/') / '__init__.py'
        bpy_types_pyi.parent.mkdir(parents=True, exist_ok=True)
        print(bpy_types_pyi)
        with open(bpy_types_pyi, 'w') as w:
            w.write(
                'from typing import Any, Tuple, List, Generic, TypeVar, Iterator, overload\n'
            )
            w.write('from mathutils import Vector, Matrix\n')
            w.write('\n')
            w.write('\n')

            # prefix
            w.write(prev)
            w.write('\n')

            # types
            for t in self.enumerate():
                w.write(t.to_str(self.types))
                w.write('\n')
                w.write('\n')

            # suffix
            for a in additional:
                w.write(f'{a}\n')


RET = ':return:'
RT = ':rtype:'
# ':rtype: :class:`Color`.. note:: use this to get a copy of a wrapped color withno reference to the original data.'
RT_PATTERN = re.compile(r':rtype:\s*:class:`(\w+)`')
ARG = ':arg '
TP = ':type '


def split_doc(doc: str):
    splited = re.split(r'\n+', doc, maxsplit=2)
    num = len(splited)
    if num == 3:
        return (x.strip() for x in splited)
    elif num == 2:
        return splited[0].strip(), splited[1].strip(), ''
    else:
        return splited[0].strip(), '', ''


class ParseFunction:
    def __init__(self, name: str, doc: str):
        self.name = name
        self.params = []
        self.rtypes = []

        _summary, _description, params_rtype = split_doc(doc)

        if params_rtype:
            current = ''
            for l in params_rtype.splitlines():
                l = l.strip()
                if l.startswith(RET):
                    self._append(current)
                    current = l
                elif l.startswith(RT):
                    self._append(current)
                    current = l
                elif l.startswith(ARG):
                    self._append(current)
                    current = l
                elif l.startswith(TP):
                    self._append(current)
                    current = l
                else:
                    current += l
            self._append(current)

    def _append(self, src: str):
        if not src:
            return

        m = RT_PATTERN.match(src)
        if m:
            self.rtypes.append(m[1])
        elif src.startswith(RT):
            splitted = src[len(RT):].split(':')
            if len(splitted) == 1:
                self.rtypes.append(splitted[0])
            else:
                name = splitted[0]
                param_type = splitted[1]
                self.rtypes.append(FACTORY.from_name(param_type.strip()))
        elif src.startswith(TP):
            splitted = src[len(TP):].split(':')
            name = splitted[0]
            param_type = splitted[1]
            self.params.append(
                f'{name.strip()}: {FACTORY.from_name(param_type.strip())}')
        # elif src == ':param rgb: (r, g, b) color values':
        #     self.params.append('rgb: Tuple[float, float, float]')
        # elif src == ':param seq: size 3 or 4':
        #     self.params.append('seq: Sequence[float]')
        else:
            a = 0

    def write_to(self, w: TextIOWrapper, isMethod: bool):
        w.write(format_function(self.name, isMethod, self.params, self.rtypes))


class ParseClass:
    def __init__(self, name: str, klass: type):
        self.name = name
        self.props = []
        self.methods: List[ParseFunction] = []

        if klass.__doc__:
            # constructor
            if self.name == 'Quaternion':
                constructor = ParseFunction('__init__', '')
                constructor.params.append('*args')
                self.methods.append(constructor)
            else:
                self.methods.append(ParseFunction('__init__', klass.__doc__))

        for k, v in klass.__dict__.items():
            if k.startswith('__'):
                continue
            attr_type = type(v)
            if attr_type == types.GetSetDescriptorType:
                if v.__doc__:
                    m = re.search(r':type:\s*(.*)$', v.__doc__)
                    if m:
                        t = FACTORY.from_name(m.group(1))
                        self.props.append(f'    {k}: {t}\n')

            elif attr_type == types.MethodDescriptorType:
                if v.__doc__:
                    self.methods.append(ParseFunction(k, v.__doc__))
            else:
                # print(name, k, attr_type, v)
                pass

    def write_to(self, w: TextIOWrapper):
        w.write(f'class {self.name}:\n')
        if self.methods or self.props:
            for p in self.props:
                w.write(p)
            for m in self.methods:
                m.write_to(w, True)
                w.write('\n')
        else:
            w.write(f'    pass\n')


class StubGenerator:
    '''
    blender/doc/python_api/sphinx_doc_gen.py
    '''
    def __init__(self):
        self.stub_module_map: Dict[str, StubModule] = {}

    def get_or_create_stub_module(self, name: str) -> StubModule:
        stub_module = self.stub_module_map.get(name)
        if stub_module:
            return stub_module

        stub_module = StubModule(name)
        self.stub_module_map[name] = stub_module
        return stub_module

    def generate(self):
        '''
        generate stubs files for bpy module, mathutils... etc
        '''

        # read all data:
        structs, funcs, ops, props = rna_info.BuildRNAInfo()

        for s in structs.values():
            stub_module = self.get_or_create_stub_module(s.module_name)
            stub_module.push(s)

        # __init__.pyi
        bpy_pyi: pathlib.Path = BL_DIR / 'bpy/__init__.pyi'
        bpy_pyi.parent.mkdir(parents=True, exist_ok=True)
        with open(bpy_pyi, 'w') as w:
            w.write('from . import types, utils, ops\n')
            ## add
            w.write('data: types.BlendData\n')
            # Changes in Blender will force errors here
            context_type_map = {
                # context_member: (RNA type, is_collection)
                "active_annotation_layer": ("GPencilLayer", False),
                "active_base": ("ObjectBase", False),
                "active_bone": ("EditBone", False),
                "active_gpencil_frame": ("GreasePencilLayer", True),
                "active_gpencil_layer": ("GPencilLayer", True),
                "active_node": ("Node", False),
                "active_object": ("Object", False),
                "active_operator": ("Operator", False),
                "active_pose_bone": ("PoseBone", False),
                "active_editable_fcurve": ("FCurve", False),
                "annotation_data": ("GreasePencil", False),
                "annotation_data_owner": ("ID", False),
                "armature": ("Armature", False),
                "bone": ("Bone", False),
                "brush": ("Brush", False),
                "camera": ("Camera", False),
                "cloth": ("ClothModifier", False),
                "collection": ("LayerCollection", False),
                "collision": ("CollisionModifier", False),
                "curve": ("Curve", False),
                "dynamic_paint": ("DynamicPaintModifier", False),
                "edit_bone": ("EditBone", False),
                "edit_image": ("Image", False),
                "edit_mask": ("Mask", False),
                "edit_movieclip": ("MovieClip", False),
                "edit_object": ("Object", False),
                "edit_text": ("Text", False),
                "editable_bones": ("EditBone", True),
                "editable_gpencil_layers": ("GPencilLayer", True),
                "editable_gpencil_strokes": ("GPencilStroke", True),
                "editable_objects": ("Object", True),
                "editable_fcurves": ("FCurve", True),
                "fluid": ("FluidSimulationModifier", False),
                "gpencil": ("GreasePencil", False),
                "gpencil_data": ("GreasePencil", False),
                "gpencil_data_owner": ("ID", False),
                "hair": ("Hair", False),
                "image_paint_object": ("Object", False),
                "lattice": ("Lattice", False),
                "light": ("Light", False),
                "lightprobe": ("LightProbe", False),
                "line_style": ("FreestyleLineStyle", False),
                "material": ("Material", False),
                "material_slot": ("MaterialSlot", False),
                "mesh": ("Mesh", False),
                "meta_ball": ("MetaBall", False),
                "object": ("Object", False),
                "objects_in_mode": ("Object", True),
                "objects_in_mode_unique_data": ("Object", True),
                "particle_edit_object": ("Object", False),
                "particle_settings": ("ParticleSettings", False),
                "particle_system": ("ParticleSystem", False),
                "particle_system_editable": ("ParticleSystem", False),
                "pointcloud": ("PointCloud", False),
                "pose_bone": ("PoseBone", False),
                "pose_object": ("Object", False),
                "scene": ("Scene", False),
                "sculpt_object": ("Object", False),
                "selectable_objects": ("Object", True),
                "selected_bones": ("EditBone", True),
                "selected_editable_bones": ("EditBone", True),
                "selected_editable_fcurves": ("FCurve", True),
                "selected_editable_objects": ("Object", True),
                "selected_editable_sequences": ("Sequence", True),
                "selected_nla_strips": ("NlaStrip", True),
                "selected_nodes": ("Node", True),
                # "selected_objects": ("Object", True),
                "selected_pose_bones": ("PoseBone", True),
                "selected_pose_bones_from_active_object": ("PoseBone", True),
                "selected_sequences": ("Sequence", True),
                "selected_visible_fcurves": ("FCurve", True),
                "sequences": ("Sequence", True),
                "soft_body": ("SoftBodyModifier", False),
                "speaker": ("Speaker", False),
                "texture": ("Texture", False),
                "texture_slot": ("MaterialTextureSlot", False),
                "texture_user": ("ID", False),
                "texture_user_property": ("Property", False),
                "vertex_paint_object": ("Object", False),
                "view_layer": ("ViewLayer", False),
                "visible_bones": ("EditBone", True),
                "visible_gpencil_layers": ("GPencilLayer", True),
                "visible_objects": ("Object", True),
                "visible_pose_bones": ("PoseBone", True),
                "visible_fcurves": ("FCurve", True),
                "weight_paint_object": ("Object", False),
                "volume": ("Volume", False),
                "world": ("World", False),
            }
            w.write('''
class Context(types.Context):
    selected_objects: types.bpy_prop_collection[types.Object]
context: Context
''')

        for k, v in self.stub_module_map.items():
            if k == 'bpy.types':
                v.generate(
                    BL_DIR, '''T = TypeVar('T')
class bpy_prop_collection(Generic[T]):
    def __len__(self) -> int: ... # noqa
    @overload
    def __getitem__(self, i) -> T: ... # noqa
    @overload
    def __getitem__(self, s: slice) -> 'bpy_prop_collection[T]': ... # noqa
    def __iter__(self) -> Iterator[T]: ... # noqa
    def find(self, key: str) -> int: ... # noqa
    def get(self, key, default=None): ... # noqa
    def items(self): ... # noqa
    def keys(self): ... # noqa
    def values(self): ... # noqa

''', ['VIEW3D_MT_object: List[Any]'])
            else:
                print(k)

        # standalone modules
        self.generate_module(mathutils)
        self.generate_module(bpy.utils)
        self.generate_module(bpy.props)
        self.generate_module(bpy.ops, 'bpy.ops')
        self.generate_module(bpy_extras.io_utils)
        self.generate_module(bpy_extras.image_utils)

    def generate_module(self, m: types.ModuleType, module_name=''):
        '''
        pymodule2sphinx
        py_descr2sphinx
        '''

        module_name = module_name if module_name else m.__name__
        bpy_pyi: pathlib.Path = BL_DIR / f'{module_name.replace(".", "/")}/__init__.pyi'
        bpy_pyi.parent.mkdir(parents=True, exist_ok=True)

        with open(bpy_pyi, 'w') as w:
            w.write('''from typing import Tuple, List, Any, Callable, Sequence
import bpy
import datetime
''')
            if module_name != 'mathutils':
                w.write('from mathutils import Vector\n')
            w.write('\n')

            if ismodule(m):
                for name, klass in inspect.getmembers(m, inspect.isclass):
                    ParseClass(name, klass).write_to(w)
                    w.write('\n')
                    w.write('\n')

                for name, func in inspect.getmembers(m, inspect.isroutine):
                    if name.endswith('Property'):
                        w.write(f'def {name}(**kw) -> Any: ... # noqa\n')

                    else:
                        if func.__doc__:
                            if name in ['register_class', 'unregister_class']:
                                w.write(
                                    format_function(name, False, [
                                        StubProperty('klass', FACTORY.any_type)
                                    ], []))
                            else:
                                func = ParseFunction(name,
                                                     func.__doc__).write_to(
                                                         w, False)
                            w.write('\n')
                        else:
                            print(name, func)
            else:
                if str(type(m)) == "<class 'bpy.ops.BPyOps'>":
                    for key in dir(m):
                        attr = getattr(m, key)
                        if str(type(attr)) == "<class 'bpy.ops.BPyOpsSubMod'>":
                            self.generate_module(attr, f'{module_name}.{key}')
                            w.write(f'from . import {key}\n')
                else:
                    for key in dir(m):
                        attr = getattr(m, key)
                        w.write(f'def {key}(*args, **kw): ... # noqa\n')


if __name__ == "__main__":
    generator = StubGenerator()
    generator.generate()
