import argparse
import pathlib
import subprocess
import sys
import os
import shutil
import re
from typing import List, Tuple
from contextlib import contextmanager
import vcenv

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
    if not p.stdout:
        raise Exception("fail to popen")
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
        self.version = self.tag
        if re.match(r'v\d.\d\d.\d', self.tag):

            self.version = f'blender-{self.tag}-release'

        self.workspace = workspace
        self.bpy_dir: pathlib.Path = self.workspace / ('bpy_' + tag)
        self.bin_dir: pathlib.Path = self.workspace / ('bin_' + tag)
        self.repository: pathlib.Path = self.workspace / 'blender'
        self.encoding = encoding
        self.bin_install_dir = self.workspace / 'install'

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
                ret, _ = run_command(f'git switch -f {self.version}')
                ret, _ = run_command('git restore .')
                if self.version == 'master':
                    ret, _ = run_command(f'git pull origin {self.version}')
                ret, _ = run_command('git submodule update --init --recursive')
                ret, _ = run_command('git status')

                # patch
                # # uncached vars
                # set(PYTHON_INCLUDE_DIRS "${PYTHON_INCLUDE_DIR}")
                # set(PYTHON_LIBRARIES debug "${PYTHON_LIBRARY_DEBUG}" optimized "${PYTHON_LIBRARY}" )
                path = current / 'build_files/cmake/platform/platform_win32.cmake'
                lines = []
                d = str(PY_DIR).replace("\\", "/")
                v = sys.version_info
                for line in path.read_text().splitlines():
                    if re.match(r'^\s*set\(PYTHON_INCLUDE_DIRS ', line):
                        line = f'set(PYTHON_INCLUDE_DIRS "{d}/include")'
                    elif re.match(r'^\s*set\(PYTHON_LIBRARIES ', line):
                        line = f'set(PYTHON_LIBRARIES "{d}/libs/python{v.major}{v.minor}.lib")'
                    lines.append(line + '\n')
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

    def clear(self, dir: pathlib.Path) -> None:
        '''
        remove cmake build_dir
        '''
        shutil.rmtree(dir, ignore_errors=True)

    def cmake(self, is_bpy: bool) -> pathlib.Path:
        '''
        generate vc solutions to build_dir
        '''
        if is_bpy:
            dir = self.bpy_dir
            cmake_args = f'{python_define()} -DWITH_PYTHON_INSTALL=OFF -DWITH_PYTHON_INSTALL_NUMPY=OFF -DWITH_PYTHON_MODULE=ON '
        else:
            dir = self.bin_dir
            cmake_args = ''
        dir.mkdir(parents=True, exist_ok=True)

        cmake = get_cmake()
        vcenv.update_environ()

        # https://devtalk.blender.org/t/bpy-module-dll-load-failed/11765
        with pushd(dir):
            run_command(
                f'{cmake} -B . -S ../blender -G Ninja -DCMAKE_BUILD_TYPE=Release {cmake_args} -DWITH_OPENCOLLADA=OFF -DWITH_AUDASPACE=OFF -DWITH_WINDOWS_BUNDLE_CRT=OFF'
            )

        return dir

    def build(self, dir: pathlib.Path) -> None:
        '''
        run msbuild
        '''
        print('build', dir)
        cmake = get_cmake()

        with pushd(dir):
            run_command(f'{cmake} --build . --config Release',
                        encoding=self.encoding)

    def install_bin(self) -> None:
        cmake = get_cmake()
        with pushd(self.bin_dir):
            run_command(
                f'{cmake} --install . --config Release --prefix {self.bin_install_dir}',
                encoding=self.encoding)

    def install_bpy(self) -> None:
        '''
        copy bpy.pyd and *.dll and *.py to python lib folder
        '''
        print('install')

        shutil.rmtree(BL_DIR, ignore_errors=True)

        with (PY_DIR / 'Lib/site-packages/blender.pth').open('w') as w:
            w.write("blender")

        BL_DIR.mkdir(parents=True, exist_ok=True)

        # with pushd(self.build_dir / 'bin/Release'):
        #     # src_dll = next(iter(glob.glob('python*.dll')))
        #     # dst_dll = BL_DIR / src_dll
        #     # if src_dll[6] != str(sys.version_info.major):
        #     #     raise Exception()
        #     # if src_dll[7] != str(sys.version_info.minor):
        #     #     raise Exception()

        #     shutil.copy('bpy.pyd', BL_DIR)
        cmake = get_cmake()
        with pushd(self.bpy_dir):
            run_command(
                f'{cmake} --install . --config Release --prefix {BL_DIR}',
                encoding=self.encoding)

        def get_dir():
            for f in BL_DIR.iterdir():
                if f.is_dir() and re.match(r'\d.\d+', f.name):
                    return f

        bl_scripts = get_dir()
        if bl_scripts:
            src = bl_scripts
            dst = PY_DIR / bl_scripts.name
            if dst.exists():
                print(f'remove {dst}')
                shutil.rmtree(dst)
            print(f'copy {src} to {dst}')
            shutil.copytree(src, dst)


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

    get_msbuild()
    get_cmake()

    parser = argparse.ArgumentParser('blender module builder')
    parser.add_argument("--update", action='store_true')
    parser.add_argument("--clean", action='store_true')
    parser.add_argument("--bpy", action='store_true')
    parser.add_argument("--bin", action='store_true')
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
        builder.clear(builder.bpy_dir)
        builder.clear(builder.bin_dir)
    if parsed.bpy:
        dir = builder.cmake(is_bpy=True)
        builder.build(dir)
        builder.install_bpy()
    if parsed.bin:
        dir = builder.cmake(is_bpy=False)
        builder.build(dir)
        builder.install_bin()


if __name__ == '__main__':
    main()
