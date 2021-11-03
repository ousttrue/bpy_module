import pathlib

HERE = pathlib.Path(__file__).absolute().parent
CLONE_DIR = HERE / 'blender'

from git.repo import Repo

REPO = Repo(CLONE_DIR)

from doit.action import CmdAction

CONFIGURE_FLAGS = ' '.join([
    '-DWITH_INPUT_NDOF=OFF', '-DWITH_CYCLES=OFF', '-DWITH_OPENVDB=OFF',
    '-DWITH_LIBMV=OFF'
])

BPY_FLAGS = ' '.join([
    '-DWITH_PYTHON_INSTALL=OFF', '-DWITH_PYTHON_INSTALL_NUMPY=OFF',
    '-DWITH_PYTHON_MODULE=ON'
])


def task_bpy_build():
    if not REPO:
        return
    for tag in REPO.tags:
        base_dir = HERE / f'tags/{tag.name}'
        workspace = base_dir / 'blender'
        build = base_dir / 'bpy'
        yield {
            'name':
            tag.name,
            'verbosity':
            2,
            'actions': [
                CmdAction(
                    f'cmake -S blender -B bpy -G Ninja {CONFIGURE_FLAGS} {BPY_FLAGS}',
                    cwd=base_dir),
                CmdAction(f'cmake --build bpy', cwd=base_dir)
            ],
        }
