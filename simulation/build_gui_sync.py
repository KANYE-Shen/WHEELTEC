"""Build the project-local Gazebo GUI plugin into the D-backed Linux workspace."""
import os
from pathlib import Path
import subprocess


def ensure_gui_sync():
    source = Path(__file__).resolve().parent/'gui_sync'
    build = Path.home()/'wheeltec_sim_ws/build/gui_sync'
    library = build/'libWheeltecRenderSync.so'
    stamp = build/'.wheeltec-gui-sync-built'
    inputs = [p for p in source.iterdir() if p.is_file()]
    if library.is_file() and stamp.is_file() and all(p.stat().st_mtime <= stamp.stat().st_mtime for p in inputs):
        return build
    # Exclude Windows PATH entries from CMake dependency probing over /mnt/c.
    env = dict(os.environ, PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin')
    subprocess.run(['cmake', '-S', str(source), '-B', str(build),
                    '-DCMAKE_BUILD_TYPE=Release'], env=env, check=True)
    subprocess.run(['cmake', '--build', str(build), '--parallel', '2'], env=env, check=True)
    stamp.touch()
    return build


if __name__ == '__main__':
    print(ensure_gui_sync())
