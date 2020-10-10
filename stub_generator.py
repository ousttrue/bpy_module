import io
import types
import inspect
import pathlib
import sys
import re
from typing import List, Dict, NamedTuple, Optional

HERE = pathlib.Path(__file__).parent
PY_DIR = pathlib.Path(sys.executable).parent
BL_DIR = PY_DIR / 'Lib/site-packages/blender'

PYTHON_TYPE_MAP = {
    'string': 'str',
    'boolean': 'bool',
    'bool': 'bool',
    'int': 'int',
    'float': 'float',
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
}


def get_python_type(prop) -> str:
    if (prop.type == 'collection'):
        return f"collections.abc.Sequence['{prop.fixed_type.identifier}']"

    value_type = PYTHON_TYPE_MAP.get(prop.type, 'Any')
    if prop.array_length == 0:
        return value_type

    if value_type == 'float':
        if prop.array_length == 9:
            return 'Matrix'
        if prop.array_length == 16:
            return 'Matrix'
        return 'Vector'

    values = ', '.join([value_type] * prop.array_length)
    return f'Tuple[{values}]'


class StubProperty(NamedTuple):
    name: str
    type: str

    def __str__(self) -> str:
        return f'{self.name}: {self.type}'

    @staticmethod
    def from_rna(prop) -> 'StubProperty':
        return StubProperty(prop.identifier, get_python_type(prop))


class StubFunction(NamedTuple):
    name: str
    ret_types: List[str]
    params: List[StubProperty]
    is_method: bool

    def __str__(self) -> str:
        params = [str(param) for param in self.params]
        self_arg = 'self, ' if self.is_method else ''
        if not self.ret_types:
            return f'def {self.name}({self_arg}{", ".join(params)}) -> None: ... # noqa'
        elif len(self.ret_types) == 1:
            return f'def {self.name}({self_arg}{", ".join(params)}) -> {self.ret_types[0]}: ... # noqa'
        else:
            return f'def {self.name}({self_arg}{", ".join(params)}) -> Tuple[{", ".join(self.ret_types)}]: ... # noqa'

    @staticmethod
    def from_rna(func, is_method: bool) -> 'StubFunction':
        ret_values = [get_python_type(v) for v in func.return_values]
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

    def generate(self, dir: pathlib.Path):
        bpy_types_pyi: pathlib.Path = dir / self.name.replace(
            '.', '/') / '__init__.py'
        bpy_types_pyi.parent.mkdir(parents=True, exist_ok=True)
        print(bpy_types_pyi)
        with open(bpy_types_pyi, 'w') as w:
            w.write('from typing import Any, Tuple\n')
            w.write('from mathutils import Vector, Matrix\n')
            w.write('import collections.abc\n')
            w.write('\n')
            w.write('\n')
            for t in self.enumerate():
                w.write(str(t))
                w.write('\n')
                w.write('\n')


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
            w.write('from . import types\n')
            ## add
            w.write('data: types.BlendData\n')

        for k, v in self.stub_module_map.items():
            if k == 'bpy.types':
                v.generate(BL_DIR)
            else:
                print(k)

        # mathutil
        import mathutils
        self.generate_module(mathutils)

    def generate_module(self, m: types.ModuleType):
        '''
        pymodule2sphinx
        py_descr2sphinx
        '''
        bpy_pyi: pathlib.Path = BL_DIR / f'{m.__name__}/__init__.pyi'
        bpy_pyi.parent.mkdir(parents=True, exist_ok=True)

        def to_python_type(doc: str) -> str:
            if doc.startswith('string '):
                return f'str #{doc}'
            return PYTHON_TYPE_MAP[doc]

        with open(bpy_pyi, 'w') as w:
            w.write('from typing import Tuple\n')
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
                                t = to_python_type(m.group(1))
                                w.write(f'    {k}: {t}\n')
                        counter += 1
                    elif attr_type == types.MethodDescriptorType:
                        if v.__doc__:
                            m = re.search(r':rtype:\s*(.*)$', v.__doc__)
                            if m:
                                t = to_python_type(m.group(1))
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


if __name__ == "__main__":
    generator = StubGenerator()
    generator.generate()
