import argparse
import pathlib
import subprocess
import sys
import os
import io
import shutil
import multiprocessing
import glob
import re
from typing import List, Tuple, Dict, NamedTuple, Optional
from contextlib import contextmanager

GIT_BLENDER = 'git://git.blender.org/blender.git'
HERE = pathlib.Path(__file__).parent
VSWHERE = HERE / 'vswhere.exe'
PY_DIR = pathlib.Path(sys.executable).parent
BL_DIR = PY_DIR / 'Lib/site-packages/blender'


def python_define():
    v = sys.version_info
    d = str(PY_DIR).replace("\\", "/")
    return f'-DPYTHON_VERSION={v.major}.{v.minor}.{v.micro} -DPYTHON_ROOT_DIR={d} -DPYTHON_INCLUDE_DIRS={d}/include -DPYTHON_LIBRARIES={d}/libs/python{v.major}.{v.minor}.lib'


@contextmanager
def pushd(new_dir):
    previous_dir = os.getcwd()
    print(f'pushd: {new_dir}')
    pathlib.Path(new_dir).mkdir(exist_ok=True, parents=True)
    os.chdir(new_dir)
    try:
        yield pathlib.Path('.').absolute()
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
    if not outs:
        # fallback
        ret, outs = run_command(
            f'{VSWHERE} -products Microsoft.VisualStudio.Product.BuildTools -requires Microsoft.Component.MSBuild -find MSBuild\**\Bin\MSBuild.exe'
        )
    return pathlib.Path(
        f'{outs[0]}/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'
    )


def get_msbuild() -> pathlib.Path:
    ret, outs = run_command(
        f'{VSWHERE} -latest -requires Microsoft.Component.MSBuild -find MSBuild\**\Bin\MSBuild.exe'
    )
    if not outs:
        # fallback
        ret, outs = run_command(
            f'{VSWHERE} -products Microsoft.VisualStudio.Product.BuildTools -requires Microsoft.Component.MSBuild -find MSBuild\**\Bin\MSBuild.exe'
        )
    return pathlib.Path(outs[0])


def get_codepage() -> int:
    try:
        ret, outs = run_command("chcp.com", "utf-8")
        # Active code page: 65001
        return int(outs[0].split(':')[1].strip())
    except Exception:
        ret, outs = run_command("chcp.com", "cp932")
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

            with pushd('blender') as current:
                # switch branch
                ret, _ = run_command(f'git switch blender-{self.tag}-release')
                ret, _ = run_command(f'git restore .')
                ret, _ = run_command(
                    f'git submodule update --init --recursive')
                ret, _ = run_command(f'git status')

                # patch
                # # uncached vars
                # set(PYTHON_INCLUDE_DIRS "${PYTHON_INCLUDE_DIR}")
                # set(PYTHON_LIBRARIES debug "${PYTHON_LIBRARY_DEBUG}" optimized "${PYTHON_LIBRARY}" )
                path = current / 'build_files/cmake/platform/platform_win32.cmake'
                lines = []
                d = str(PY_DIR).replace("\\", "/")
                v = sys.version_info
                for l in path.read_text().splitlines():
                    if re.match(r'^\s*set\(PYTHON_INCLUDE_DIRS ', l):
                        l = f'set(PYTHON_INCLUDE_DIRS "{d}/include")'
                    elif re.match(r'^\s*set\(PYTHON_LIBRARIES ', l):
                        l = f'set(PYTHON_LIBRARIES "{d}/libs/python{v.major}{v.minor}.lib")'
                    lines.append(l + '\n')
                with path.open('w') as w:
                    w.writelines(lines)

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

        # https://devtalk.blender.org/t/bpy-module-dll-load-failed/11765
        with pushd(self.build_dir):
            run_command(
                f'{cmake} ../blender {python_define()} -DWITH_PYTHON_INSTALL=OFF -DWITH_PYTHON_INSTALL_NUMPY=OFF -DWITH_PYTHON_MODULE=ON -DWITH_OPENCOLLADA=OFF -DWITH_AUDASPACE=OFF -DWITH_WINDOWS_BUNDLE_CRT=OFF'
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
            vcxproj = pathlib.Path('INSTALL.vcxproj')
            if not vcxproj.exists():
                raise f'{vcxproj} not exists'
            run_command(
                f'{msbuild} {vcxproj} -maxcpucount:{count} -p:configuration=Release',
                encoding=self.encoding)

    def install(self) -> None:
        '''
        copy bpy.pyd and *.dll and *.py to python lib folder
        '''
        with pushd(self.build_dir / 'bin/Release'):
            # src_dll = next(iter(glob.glob('python*.dll')))
            # dst_dll = BL_DIR / src_dll
            # if src_dll[6] != str(sys.version_info.major):
            #     raise Exception()
            # if src_dll[7] != str(sys.version_info.minor):
            #     raise Exception()

            with (PY_DIR / 'Lib/site-packages/blender.pth').open('w') as w:
                w.write("blender")

            BL_DIR.mkdir(parents=True, exist_ok=True)

            shutil.copy('bpy.pyd', BL_DIR)
            for f in glob.glob('*.dll'):
                if f.startswith('python'):
                    continue
                print(f'{f} => {BL_DIR / f}')
                shutil.copy(f, BL_DIR / f)
            for f in glob.glob('*.pdb'):
                print(f'{f} => {BL_DIR / f}')
                shutil.copy(f, BL_DIR / f)

            bl_version = self.tag[1:]
            dst = PY_DIR / bl_version
            if dst.exists():
                print(f'remove {dst}')
                shutil.rmtree(dst)
            current = pathlib.Path('.').absolute()
            print(f'copy {current / bl_version} => {dst}')
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

    def enable_base(self, used) -> bool:
        if not self.base:
            return True
        for u in used:
            if self.base == u.name:
                return True
        return False

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
            w.write('\n')
            w.write('\n')
            for t in self.enumerate():
                w.write(str(t))
                w.write('\n')
                w.write('\n')


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
            stub_module.push(s)

        # __init__.pyi
        bpy_pyi: pathlib.Path = BL_DIR / 'bpy/__init__.pyi'
        bpy_pyi.parent.mkdir(parents=True, exist_ok=True)
        with open(bpy_pyi, 'w') as w:
            w.write('from. import types')

        for k, v in self.stub_module_map.items():
            if k == 'bpy.types':
                v.generate(BL_DIR)


def main():
    if sys.version_info.major != 3:
        raise Exception()

    try:
        ret, _ = run_command('git --version')
    except FileNotFoundError as ex:
        print(ex)
        return
    try:
        ret, _ = run_command('svn --version --quiet')
    except FileNotFoundError as ex:
        print(ex)
        return
    try:
        get_msbuild()
    except:
        print('msbuild not found')
        return
    try:
        print('cmake not found')
        get_cmake()
    except:
        return

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
