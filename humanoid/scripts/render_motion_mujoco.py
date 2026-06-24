import argparse, os, shutil, subprocess, tempfile
from pathlib import Path
import numpy as np
if "MUJOCO_GL" not in os.environ and os.name != "nt":
    os.environ["MUJOCO_GL"] = "glx"
import imageio.v2 as imageio
import mujoco

p = argparse.ArgumentParser()
p.add_argument("--csv", required=True, type=Path)
p.add_argument("--mjcf", required=True, type=Path)
p.add_argument("--output", required=True, type=Path)
p.add_argument("--width", type=int, default=640)
p.add_argument("--height", type=int, default=480)
p.add_argument("--start", type=int, default=0)
p.add_argument("--end", type=int, default=-1)
p.add_argument("--joint-unit", choices=("radians", "degrees"), default="radians")
args = p.parse_args()

header = args.csv.read_text(encoding="utf-8-sig").splitlines()[0].split(",")
data = np.genfromtxt(args.csv, delimiter=",", skip_header=1)
if data.ndim == 1:
    data = data[None, :]
time_col = "timestamp" if "timestamp" in header else "time"
if time_col not in header:
    raise ValueError("CSV must contain either a timestamp or time column")
time_idx = header.index(time_col)
fps = 1.0 / np.diff(data[:, time_idx]).mean()
end = len(data) if args.end < 0 else min(args.end, len(data))
data = data[args.start:end]

model = mujoco.MjModel.from_binary_path(str(args.mjcf)) if str(args.mjcf).endswith('.mjb') else mujoco.MjModel.from_xml_path(str(args.mjcf))
mdata = mujoco.MjData(model)
qpos_adr = []
joint_columns = []
for name in header:
    if not name.endswith("_joint"):
        continue
    jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
    if jid < 0:
        raise ValueError(f"CSV joint column is missing from MuJoCo model: {name}")
    joint_columns.append(header.index(name))
    qpos_adr.append(model.jnt_qposadr[jid])
qpos_adr = np.array(qpos_adr)
joint_columns = np.array(joint_columns)
if not len(qpos_adr):
    raise ValueError("CSV contains no joint position columns ending in _joint")
joint_scale = np.pi / 180.0 if args.joint_unit == "degrees" else 1.0

required_root_columns = [
    "root_pos_x",
    "root_pos_y",
    "root_pos_z",
    "root_quat_w",
    "root_quat_x",
    "root_quat_y",
    "root_quat_z",
]
missing_root_columns = [name for name in required_root_columns if name not in header]
if missing_root_columns:
    raise ValueError(f"CSV is missing root pose columns: {missing_root_columns}")
root_indices = {name: header.index(name) for name in required_root_columns}

model.vis.quality.offsamples = 0
model.vis.quality.shadowsize = 0
renderer = mujoco.Renderer(model, args.height, args.width)
cam = mujoco.MjvCamera()
cam.distance, cam.elevation, cam.azimuth = 2.6, -15.0, 135.0
args.output.parent.mkdir(parents=True, exist_ok=True)
writer_kwargs = {"fps": round(fps)}
if args.output.suffix.lower() in {".mp4", ".m4v", ".mov"}:
    writer_kwargs.update(codec="libx264", quality=7, macro_block_size=1)
frame_dir = None
writer = None
try:
    writer = imageio.get_writer(str(args.output), **writer_kwargs)
except ValueError:
    if not shutil.which("ffmpeg"):
        raise
    frame_dir = tempfile.TemporaryDirectory(prefix="mujoco_frames_")

for frame_idx, row in enumerate(data):
    mdata.qpos[0:3] = [
        row[root_indices["root_pos_x"]],
        row[root_indices["root_pos_y"]],
        row[root_indices["root_pos_z"]],
    ]
    mdata.qpos[3:7] = [
        row[root_indices["root_quat_w"]],
        row[root_indices["root_quat_x"]],
        row[root_indices["root_quat_y"]],
        row[root_indices["root_quat_z"]],
    ]
    mdata.qpos[qpos_adr] = row[joint_columns] * joint_scale
    mujoco.mj_forward(model, mdata)
    cam.lookat[:] = mdata.qpos[0:3]
    renderer.update_scene(mdata, camera=cam)
    frame = renderer.render()
    if writer is not None:
        writer.append_data(frame)
    else:
        imageio.imwrite(
            os.path.join(frame_dir.name, f"frame_{frame_idx:06d}.png"),
            frame,
        )
if writer is not None:
    writer.close()
else:
    suffix = args.output.suffix.lower()
    if suffix == ".gif":
        gif_fps = min(25, round(fps))
        vf = "fps={0},scale={1}:{2}:flags=lanczos".format(gif_fps, args.width, args.height)
        cmd = [
            "ffmpeg", "-y", "-framerate", str(round(fps)),
            "-i", os.path.join(frame_dir.name, "frame_%06d.png"),
            "-vf", vf,
            str(args.output),
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-framerate", str(round(fps)),
            "-i", os.path.join(frame_dir.name, "frame_%06d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(args.output),
        ]
    subprocess.run(cmd, check=True)
    frame_dir.cleanup()
print(f"wrote {args.output} ({len(data)} frames @ {fps:.1f} fps)")



