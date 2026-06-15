import argparse, os
from pathlib import Path
import numpy as np
os.environ.setdefault("MUJOCO_GL", "glx")
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
args = p.parse_args()

header = args.csv.read_text().splitlines()[0].split(",")
data = np.genfromtxt(args.csv, delimiter=",", skip_header=1)
fps = 1.0 / np.diff(data[:, 0]).mean()
end = len(data) if args.end < 0 else min(args.end, len(data))
data = data[args.start:end]

model = mujoco.MjModel.from_binary_path(str(args.mjcf)) if str(args.mjcf).endswith('.mjb') else mujoco.MjModel.from_xml_path(str(args.mjcf))
mdata = mujoco.MjData(model)
qpos_adr = []
for name in header[8:]:
    jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
    assert jid >= 0, name
    qpos_adr.append(model.jnt_qposadr[jid])
qpos_adr = np.array(qpos_adr)

model.vis.quality.offsamples = 0
model.vis.quality.shadowsize = 0
renderer = mujoco.Renderer(model, args.height, args.width)
cam = mujoco.MjvCamera()
cam.distance, cam.elevation, cam.azimuth = 2.6, -15.0, 135.0
writer = imageio.get_writer(str(args.output), fps=round(fps), codec="libx264",
                            quality=7, macro_block_size=1)
for row in data:
    mdata.qpos[0:3] = row[1:4]
    mdata.qpos[3] = row[7]
    mdata.qpos[4:7] = row[4:7]
    mdata.qpos[qpos_adr] = row[8:]
    mujoco.mj_forward(model, mdata)
    cam.lookat[:] = mdata.qpos[0:3]
    renderer.update_scene(mdata, camera=cam)
    writer.append_data(renderer.render())
writer.close()
print(f"wrote {args.output} ({len(data)} frames @ {fps:.1f} fps)")
