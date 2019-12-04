import argparse
import pathlib
import subprocess
import sys
import os
import io
import shutil
import multiprocessing
import glob
from typing import List, Tuple, Dict, NamedTuple, Optional
from contextlib import contextmanager

GIT_BLENDER = 'git://git.blender.org/blender.git'
HERE = pathlib.Path(__file__).parent
VSWHERE = HERE / 'vswhere.exe'
PY_DIR = pathlib.Path(sys.executable).parent
BL_DIR = PY_DIR / 'Lib/site-packages/blender'


@contextmanager
def pushd(new_dir):
    previous_dir = os.getcwd()
    print(f'pushd: {new_dir}')
    os.chdir(new_dir)
    try:
        yield
    finally:
        print(f'popd: {previous_dir}')
        os.chdir(previous_dir)


def run_command(cmd: str, encoding='utf-8') -> Tuple[int, List[str]]:
    print(f'# {cmd}')
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines = []
    for line_bytes in iter(p.stdout.readline, b''):
        line_bytes = line_bytes.rstrip()
        try:
            line = line_bytes.decode(encoding)
        except Exception:
            encoding = 'utf-8'
            line = line_bytes.decode(encoding)
        print(line)
        lines.append(line)
    return p.returncode, lines


def get_cmake() -> pathlib.Path:
    ret, outs = run_command(
        f'{VSWHERE} -latest -products * -requires Microsoft.VisualStudio.Component.VC.CMake.Project -property installationPath'
    )
    return pathlib.Path(
        f'{outs[0]}/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'
    )


def get_msbuild() -> pathlib.Path:
    ret, outs = run_command(
        f'{VSWHERE} -latest -requires Microsoft.Component.MSBuild -find MSBuild\**\Bin\MSBuild.exe'
    )
    return pathlib.Path(outs[0])


def get_codepage() -> int:
    ret, outs = run_command("chcp.com")
    # Active code page: 65001
    return int(outs[0].split(':')[1].strip())


def get_console_encoding() -> str:
    cp = get_codepage()
    if cp == 932:
        return 'cp932'
    elif cp == 65001:
        return 'utf-8'
    else:
        raise NotImplementedError()


class Builder:
    '''
    blender bpy module builder
    '''
    def __init__(self, tag: str, workspace: pathlib.Path, encoding: str):
        self.tag = tag
        self.workspace = workspace
        self.build_dir: pathlib.Path = self.workspace / 'build'
        self.repository: pathlib.Path = self.workspace / 'blender'
        self.encoding = encoding

    def git(self) -> None:
        '''
        clone repository and checkout specific tag version
        '''
        self.workspace.mkdir(parents=True, exist_ok=True)
        with pushd(self.workspace):
            if not self.repository.exists():
                print(f'clone: {self.repository}')
                # clone
                ret, _ = run_command(f'git clone {GIT_BLENDER} blender')
                if ret:
                    raise Exception(ret)

            with pushd('blender'):
                # switch tag
                ret, tags = run_command(f'git tag')
                if self.tag not in tags:
                    raise Exception(f'unknown tag: {self.tag}')
                ret, _ = run_command(f'git checkout refs/tags/{self.tag}')
                ret, _ = run_command(
                    f'git submodule update --init --recursive')
                ret, _ = run_command(f'git status')

    def svn(self) -> None:
        '''
        checkout svn for blender source
        '''
        # print('svn')
        make_update_py = self.repository / 'build_files/utils/make_update.py'
        with pushd(self.repository):
            run_command(f'{sys.executable} {make_update_py}')

    def clear_build_dir(self) -> None:
        '''
        remove cmake build_dir
        '''
        shutil.rmtree(self.build_dir, ignore_errors=True)

    def cmake(self) -> None:
        '''
        generate vc solutions to build_dir
        '''
        self.build_dir.mkdir(parents=True, exist_ok=True)
        cmake = get_cmake()
        with pushd(self.build_dir):
            run_command(
                f'{cmake} ../blender -DWITH_PYTHON_INSTALL=OFF -DWITH_PYTHON_INSTALL_NUMPY=OFF -DWITH_PYTHON_MODULE=ON -DWITH_OPENCOLLADA=OFF'
            )

    def build(self) -> None:
        '''
        run msbuild
        '''
        print('build')
        msbuild = get_msbuild()
        # sln = next(self.build_dir.glob('*.sln'))
        count = multiprocessing.cpu_count()
        with pushd(self.build_dir):
            run_command(
                f'{msbuild} INSTALL.vcxproj -maxcpucount:{count} -p:configuration=Release',
                encoding=self.encoding)

    def install(self) -> None:
        '''
        copy bpy.pyd and *.dll and *.py to python lib folder
        '''
        with pushd(self.build_dir / 'bin/Release'):
            src_dll = next(iter(glob.glob('python*.dll')))
            dst_dll = BL_DIR / src_dll
            if src_dll[6] != str(sys.version_info.major):
                raise Exception()
            if src_dll[7] != str(sys.version_info.minor):
                raise Exception()

            with (PY_DIR / 'Lib/site-packages/blender.pth').open('w') as w:
                w.write("blender")

            BL_DIR.mkdir(parents=True, exist_ok=True)

            shutil.copy('bpy.pyd', BL_DIR)
            for f in glob.glob('*.dll'):
                print(f'{f} => {BL_DIR / f}')
                shutil.copy(f, BL_DIR / f)
            for f in glob.glob('*.pdb'):
                print(f'{f} => {BL_DIR / f}')
                shutil.copy(f, BL_DIR / f)
            if dst_dll.exists():
                dst_dll.unlink()

            bl_version = self.tag[1:]
            dst = PY_DIR / bl_version
            if dst.exists():
                print(f'remove {dst}')
                shutil.rmtree(dst)
            print(f'copy {dst}')
            shutil.copytree(bl_version, dst)


PYTHON_TYPE_MAP = {
    'string': 'str',
    'boolean': 'bool',
    'int': 'int',
    'float': 'float',
    #
}


def get_python_type(src: str) -> str:
    if src is None:
        return None
    value = PYTHON_TYPE_MAP.get(src)
    if value:
        return value

    # print(f'not found: {src}')
    return 'Any'


class StubProperty(NamedTuple):
    name: str
    type: str

    def __str__(self) -> str:
        return f'{self.name}: {get_python_type(self.type)}'

    @staticmethod
    def from_rna(prop) -> 'StubProperty':
        # print(f'    {prop.type} {prop.identifier}')
        return StubProperty(prop.identifier, prop.type)


class StubFunction(NamedTuple):
    name: str
    ret_types: List[str]
    params: List[StubProperty]
    is_method: bool

    def __str__(self) -> str:
        params = [str(param) for param in self.params]
        ret_types = [get_python_type(ret) for ret in self.ret_types]
        self_arg = 'self, ' if self.is_method else ''
        if not self.ret_types:
            return f'def {self.name}({self_arg}{", ".join(params)}) -> None: ... # noqa'
        elif len(self.ret_types) == 1:
            return f'def {self.name}({self_arg}{", ".join(params)}) -> {get_python_type(ret_types[0])}: ... # noqa'
        else:
            return f'def {self.name}({self_arg}{", ".join(params)}) -> Tuple[{", ".join(ret_types)}]: ... # noqa'

    @staticmethod
    def from_rna(func, is_method: bool) -> 'StubFunction':
        ret_values = [v.identifier for v in func.return_values]
        args = [StubProperty.from_rna(a) for a in func.args]
        return StubFunction(func.identifier, ret_values, args, is_method)


class StubStruct(NamedTuple):
    name: str
    base: str
    properties: List[StubProperty]
    methods: List[StubFunction]

    def __str__(self) -> str:
        sio = io.StringIO()
        sio.write(f'class {self.name}')
        if self.base:
            sio.write(f'({self.base})')
        sio.write(':\n')

        if self.properties or self.methods:
            for prop in self.properties:
                sio.write(f'    {prop}\n')
            for func in self.methods:
                sio.write(f'    {func}\n')
        else:
            sio.write('    pass\n')
        return sio.getvalue()

    @staticmethod
    def from_rna(s) -> 'StubType':
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
        self.types.append(StubStruct.from_rna(_s))


class StubGenerator:
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
            if s.identifier == 'ActionFCurves':
                a = 0
            stub_module.push(s)

        bpy_pyi: pathlib.Path = BL_DIR / 'bpy/__init__.pyi'
        with open(bpy_pyi, 'w') as w:
            pass

        bpy_types_pyi: pathlib.Path = BL_DIR / 'bpy/types.pyi'
        bpy_types_pyi.parent.mkdir(parents=True, exist_ok=True)
        print(bpy_types_pyi)
        with open(bpy_types_pyi, 'w') as w:
            w.write('from typing import Any\n')
            w.write('\n')
            w.write('\n')
            for t in sorted(self.stub_module_map['bpy.types'].types,
                            key=lambda t: 1 if t.base else 0):
                w.write(str(t))
                w.write('\n')
                w.write('\n')

        for k, v in self.stub_module_map.items():
            if k == 'bpy.types':
                continue
            print(f'## {k}')
            for s in v.types:
                print(s.name)


def main():
    if sys.version_info.major != 3:
        raise Exception()

    parser = argparse.ArgumentParser('blender module builder')
    parser.add_argument("--update", action='store_true')
    parser.add_argument("--clean", action='store_true')
    parser.add_argument("--build", action='store_true')
    parser.add_argument("--install", action='store_true')
    parser.add_argument("--stubs", action='store_true')
    parser.add_argument("workspace")
    parser.add_argument("tag")
    try:
        parsed = parser.parse_args()
    except TypeError as ex:
        print(ex)
        parser.print_help()
        sys.exit(1)

    print(parsed)
    builder = Builder(parsed.tag, pathlib.Path(parsed.workspace),
                      get_console_encoding())
    if parsed.update:
        builder.git()
        builder.svn()
    if parsed.clean:
        builder.clear_build_dir()
    if parsed.build:
        builder.cmake()
        builder.build()
    if parsed.install:
        builder.install()
    if parsed.stubs:
        generator = StubGenerator()
        generator.generate()


if __name__ == '__main__':
    main()
