import argparse
import pathlib
import subprocess
import sys
import os
import shutil
import multiprocessing
import glob
from typing import List, Tuple
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
    def __init__(self, tag: str, workspace: pathlib.Path, encoding: str):
        self.tag = tag
        self.workspace = workspace
        self.build_dir: pathlib.Path = self.workspace / 'build'
        self.repository: pathlib.Path = self.workspace / 'blender'
        self.encoding = encoding

    def git(self) -> None:
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
        # print('svn')
        make_update_py = self.repository / 'build_files/utils/make_update.py'
        with pushd(self.repository):
            run_command(f'{sys.executable} {make_update_py}')

    def clear_build_dir(self) -> None:
        shutil.rmtree(self.build_dir, ignore_errors=True)

    def cmake(self) -> None:
        self.build_dir.mkdir(parents=True, exist_ok=True)
        cmake = get_cmake()
        with pushd(self.build_dir):
            run_command(
                f'{cmake} ../blender -DWITH_PYTHON_INSTALL=OFF -DWITH_PYTHON_INSTALL_NUMPY=OFF -DWITH_PYTHON_MODULE=ON -DWITH_OPENCOLLADA=OFF'
            )

    def build(self) -> None:
        print('build')
        msbuild = get_msbuild()
        sln = next(self.build_dir.glob('*.sln'))
        count = multiprocessing.cpu_count()
        with pushd(self.build_dir):
            run_command(
                f'{msbuild} INSTALL.vcxproj -maxcpucount:{count} -p:configuration=Release',
                encoding=self.encoding)

    def install(self) -> None:
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


def main():
    if sys.version_info.major != 3:
        raise Exception()

    parser = argparse.ArgumentParser('blender module builder')
    parser.add_argument("--update", action='store_true')
    parser.add_argument("--clean", action='store_true')
    parser.add_argument("--build", action='store_true')
    parser.add_argument("--install", action='store_true')
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


if __name__ == '__main__':
    main()
