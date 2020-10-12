import io
from re import split
import types
import inspect
import pathlib
import sys
import re
from typing import List, Dict, NamedTuple, Optional, Tuple

HERE = pathlib.Path(__file__).parent
PY_DIR = pathlib.Path(sys.executable).parent
BL_DIR = PY_DIR / 'Lib/site-packages/blender'

PYTHON_TYPE_MAP = {
    'str': 'str',
    'string': 'str',
    'boolean': 'bool',
    'bool': 'bool',
    'int': 'int',
    'float': 'float',
    'int or float.': 'float',
    'int, float or ``datetime.timedelta``.': 'float',
    'datetime.timedelta': 'datetime.timedelta',
    'number or a ``datetime.timedelta`` object': 'float',
    #
    'function': 'Callable[[], None]',
    'sequence': 'List[Any]',
    'class': 'type',
    'sequence of string tuples or a function': 'List[str]',
    'string or set': 'str',
    'type': 'type',
    #
    'set': 'set',
    'list': 'list',
    #
    'float triplet': 'Tuple[float, float, float]',
    'Vector': 'Vector',
    ':class:`Vector`': 'Vector',
    'Matrix Access': 'Matrix',
    ':class:`Matrix`': 'Matrix',
    ':class:`Quaternion`': 'Quaternion',
    '(:class:`Vector`, :class:`Quaternion`, :class:`Vector`)':
    'Tuple[Vector, Quaternion, Vector]',
    ':class:`Euler`': 'Euler',
    '(:class:`Vector`, float) pair': 'Tuple[Vector, float]',
    '(:class:`Quaternion`, float) pair': 'Tuple[Quaternion, float]',
    'tuple': 'List[float]',
    'tuple of strings': 'List[str]',
    'list of strings': 'List[str]',
    'collection of strings or None.': 'List[str]',
    'generator': 'List[Any]',
    'tuple pair of functions': 'Any',
    ':class:`bpy.types.WorkSpaceTool` subclass.': 'bpy.types.WorkSpaceTool',
}


def get_python_type(src: str, array_length=0) -> str:

    value_type = PYTHON_TYPE_MAP.get(src, 'Any')
    if array_length == 0:
        return value_type

    if value_type == 'float':
        if array_length == 9:
            return 'Matrix'
        if array_length == 16:
            return 'Matrix'
        return 'Vector'

    values = ', '.join([value_type] * array_length)
    return f'Tuple[{values}]'


def prop_to_python_type(prop) -> str:
    if (prop.type == 'collection'):
        return f"collections.abc.Sequence['{prop.fixed_type.identifier}']"
    return get_python_type(prop.type, prop.array_length)


class StubProperty(NamedTuple):
    name: str
    type: str

    def __str__(self) -> str:
        return f'{self.name}: {self.type}'

    @staticmethod
    def from_rna(prop) -> 'StubProperty':
        return StubProperty(prop.identifier, prop_to_python_type(prop))


def format_function(name: str, is_method: bool, params: List[str],
                    ret_types: List[str]) -> str:
    self_arg = 'self, ' if is_method else ''
    if not ret_types:
        return f'def {name}({self_arg}{", ".join(params)}) -> None: ... # noqa'
    elif len(ret_types) == 1:
        return f'def {name}({self_arg}{", ".join(params)}) -> {ret_types[0]}: ... # noqa'
    else:
        return f'def {name}({self_arg}{", ".join(params)}) -> Tuple[{", ".join(ret_types)}]: ... # noqa'


class StubFunction(NamedTuple):
    name: str
    ret_types: List[str]
    params: List[StubProperty]
    is_method: bool

    def __str__(self) -> str:
        return format_function(self.name, self.is_method,
                               [str(param) for param in self.params],
                               self.ret_types)

    @staticmethod
    def from_rna(func, is_method: bool) -> 'StubFunction':
        ret_values = [prop_to_python_type(v) for v in func.return_values]
        args = [StubProperty.from_rna(a) for a in func.args]
        return StubFunction(func.identifier, ret_values, args, is_method)


class StubStruct(NamedTuple):
    name: str
    base: Optional[str]
    properties: List[StubProperty]
    methods: List[StubFunction]

    def __str__(self) -> str:
        sio = io.StringIO()
        sio.write(f'class {self.name}')
        if self.base:
            sio.write(f'({self.base})')
        sio.write(':\n')

        if self.properties:
            for prop in self.properties:
                if self.name == 'RenderEngine' and prop.name == 'render':
                    # skip
                    continue
                sio.write(f'    {prop}\n')
        if self.methods:
            for func in self.methods:
                sio.write(f'    {func}\n')
        if not self.properties and not self.methods:
            sio.write('    pass\n')
        return sio.getvalue()

    def enable_base(self, used) -> bool:
        if not self.base:
            return True
        for u in used:
            if self.base == u.name:
                return True
        return False

    @staticmethod
    def from_rna(s) -> 'StubStruct':
        base = None
        if s.base:
            base = s.base.identifier
        return StubStruct(
            s.identifier, base,
            [StubProperty.from_rna(prop) for prop in s.properties],
            [StubFunction.from_rna(func, True) for func in s.functions])


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

        def enable(t):
            '''
            sort by inheritance
            '''
            if t.enable_base(used):
                return True

        while len(types):
            remove = []
            for t in types:
                if enable(t):
                    remove.append(t)
                    yield t
            if len(remove) == 0:
                raise Exception('Error')
            used += remove
            for r in remove:
                types.remove(r)

    def generate(self, dir: pathlib.Path, additional: List[str]):
        bpy_types_pyi: pathlib.Path = dir / self.name.replace(
            '.', '/') / '__init__.py'
        bpy_types_pyi.parent.mkdir(parents=True, exist_ok=True)
        print(bpy_types_pyi)
        with open(bpy_types_pyi, 'w') as w:
            w.write('from typing import Any, Tuple, List\n')
            w.write('from mathutils import Vector, Matrix\n')
            w.write('import collections.abc\n')
            w.write('\n')
            w.write('\n')
            for t in self.enumerate():
                w.write(str(t))
                w.write('\n')
                w.write('\n')

            for a in additional:
                w.write(f'{a}\n')


RET = ':return:'
RT = ':rtype:'
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


def parse_function(doc: str) -> Tuple[List[str], List[str]]:

    summary, description, params_rtype = split_doc(doc)

    params = []
    rtypes = []

    def append(src: str):
        if src.startswith(RT):
            name, param_type = src[len(TP):].split(':', maxsplit=1)
            rtypes.append(get_python_type(param_type.strip()))
        elif src.startswith(TP):
            name, param_type = src[len(TP):].split(':', maxsplit=1)
            params.append(
                f'{name.strip()}: {get_python_type(param_type.strip())}')

    if params_rtype:
        current = ''
        for l in params_rtype.splitlines():
            l = l.strip()
            if l.startswith(RET):
                append(current)
                current = l
            elif l.startswith(RT):
                append(current)
                current = l
            elif l.startswith(ARG):
                append(current)
                current = l
            elif l.startswith(TP):
                append(current)
                current = l
            else:
                current += l
        append(current)

    return params, rtypes


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
        import bpy
        # these two strange lines below are just to make the debugging easier (to let it run many times from within Blender)
        import imp
        import rna_info
        imp.reload(
            rna_info
        )  # to avoid repeated arguments in function definitions on second and the next runs - a bug in rna_info.py....

        # read all data:
        structs, funcs, ops, props = rna_info.BuildRNAInfo()

        for s in structs.values():
            stub_module = self.get_or_create_stub_module(s.module_name)
            stub_module.push(s)

        # __init__.pyi
        bpy_pyi: pathlib.Path = BL_DIR / 'bpy/__init__.pyi'
        bpy_pyi.parent.mkdir(parents=True, exist_ok=True)
        with open(bpy_pyi, 'w') as w:
            w.write('from . import types, utils\n')
            ## add
            w.write('data: types.BlendData\n')

        for k, v in self.stub_module_map.items():
            if k == 'bpy.types':
                v.generate(BL_DIR, ['VIEW3D_MT_object: List[Any]'])
            else:
                print(k)

        # mathutil
        import mathutils
        self.generate_module(mathutils)
        self.generate_module(bpy.utils)
        self.generate_module(bpy.props)

    def generate_module(self, m: types.ModuleType):
        '''
        pymodule2sphinx
        py_descr2sphinx
        '''

        bpy_pyi: pathlib.Path = BL_DIR / f'{m.__name__.replace(".", "/")}/__init__.pyi'
        bpy_pyi.parent.mkdir(parents=True, exist_ok=True)

        with open(bpy_pyi, 'w') as w:
            w.write('''from typing import Tuple, List, Any, Callable
import bpy
import datetime
''')
            if m.__name__ != 'mathutils':
                w.write('from mathutils import Vector\n')
            w.write('\n')

            def write_class(name: str, klass: type):
                w.write(f'class {name}:\n')
                counter = 1
                for k, v in klass.__dict__.items():
                    attr_type = type(v)
                    if attr_type == types.GetSetDescriptorType:
                        if v.__doc__:
                            m = re.search(r':type:\s*(.*)$', v.__doc__)
                            if m:
                                t = get_python_type(m.group(1))
                                w.write(f'    {k}: {t}\n')
                        counter += 1
                    elif attr_type == types.MethodDescriptorType:
                        if v.__doc__:
                            m = re.search(r':rtype:\s*(.*)$', v.__doc__)
                            if m:
                                t = get_python_type(m.group(1))
                                # w.write(f'    {k}: Callable[[], [{t}]]\n')
                                w.write(
                                    f'    def {k}(self) -> {t}: ... # noqa\n')

                    else:
                        # print(name, k, attr_type, v)
                        if k == 'to_translation':
                            print(v)
                        pass

                if counter == 0:
                    w.write(f'    pass\n')

            for name, klass in inspect.getmembers(m, inspect.isclass):
                write_class(name, klass)
                w.write('\n')
                w.write('\n')

            for name, func in inspect.getmembers(m, inspect.isroutine):
                if name.endswith('Property'):
                    w.write(f'def {name}(**kw) -> Any: ... # noqa\n')

                else:
                    if func.__doc__:
                        if name in ['register_class', 'unregister_class']:
                            w.write(
                                format_function(name, False, ['klass: Any'],
                                                []))
                        else:
                            params, rtypes = parse_function(func.__doc__)
                            w.write(
                                format_function(name, False, params, rtypes))
                        w.write('\n')
                    else:
                        print(name, func)


if __name__ == "__main__":
    generator = StubGenerator()
    generator.generate()
