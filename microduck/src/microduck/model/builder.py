"""Generate the Microduck MJCF from :mod:`microduck.model.spec`.

Two models come out of here:

``microduck.xml``
    The robot on flat ground.  Used by the walking task.
``microduck_fetch.xml``
    The same robot plus a ball and a home pad.  Used by the fetch task.

Both are regenerated with ``microduck build-model``; never hand-edit the XML.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom

from . import spec

MODEL_DIR = Path(__file__).parent
MODEL_PATH = MODEL_DIR / "microduck.xml"
FETCH_MODEL_PATH = MODEL_DIR / "microduck_fetch.xml"

#: Task-object geometry, shared by the fetch env.
BALL_RADIUS = 0.035
BALL_MASS = 0.045
HOME_RADIUS = 0.09


def _fmt(values) -> str:
    return " ".join(f"{v:.6g}" for v in values)


def _add_geom(body: ET.Element, link: spec.Link) -> None:
    kind = link.shape[0]
    attrs = {
        "name": link.name,
        "rgba": _fmt(link.rgba),
        "contype": str(link.contype),
        "conaffinity": str(link.conaffinity),
    }
    if kind == "capsule":
        _, start, end, radius = link.shape
        attrs |= {"type": "capsule", "fromto": _fmt(start + end), "size": f"{radius:.6g}"}
    else:
        _, size = link.shape
        attrs |= {"type": "box", "size": _fmt(size), "pos": _fmt(link.offset)}
    ET.SubElement(body, "geom", attrs)


def _children_of(name: str) -> list[spec.Joint]:
    return [j for j in spec.JOINTS if j.parent == name]


def _link_com(link: spec.Link) -> tuple[float, float, float]:
    if link.shape[0] == "capsule":
        _, start, end, _r = link.shape
        return tuple((a + b) / 2 for a, b in zip(start, end))  # type: ignore[return-value]
    return link.offset


def _link_inertia(link: spec.Link) -> tuple[float, float, float]:
    """Diagonal inertia of the primitive about its own centre of mass."""
    m = link.mass
    if link.shape[0] == "capsule":
        _, start, end, r = link.shape
        length = sum((b - a) ** 2 for a, b in zip(start, end)) ** 0.5
        # Cylinder plus caps, lumped as a cylinder of equal mass: accurate
        # enough at this scale and always positive definite.
        ixx = m * (3 * r * r + length * length) / 12 + m * r * r * 0.2
        izz = 0.5 * m * r * r + 1e-7
        extent = [abs(b - a) for a, b in zip(start, end)]
        out = [ixx, ixx, ixx]
        out[extent.index(max(extent)) if max(extent) > 1e-9 else 2] = izz
        return tuple(max(v, 1e-8) for v in out)  # type: ignore[return-value]
    _, (hx, hy, hz) = link.shape
    return (max(m * ((2 * hy) ** 2 + (2 * hz) ** 2) / 12, 1e-8),
            max(m * ((2 * hx) ** 2 + (2 * hz) ** 2) / 12, 1e-8),
            max(m * ((2 * hx) ** 2 + (2 * hy) ** 2) / 12, 1e-8))


def _build_body(parent_el: ET.Element, link_name: str, pos, joint: spec.Joint | None) -> None:
    link = spec.LINK_BY_NAME[link_name]
    body = ET.SubElement(parent_el, "body", {"name": link_name, "pos": _fmt(pos)})
    if joint is not None:
        servo = joint.servo
        ET.SubElement(body, "joint", {
            "name": joint.name, "type": "hinge", "axis": _fmt(joint.axis),
            "range": _fmt(joint.range), "armature": f"{servo.armature:.6g}",
            "damping": f"{servo.kd:.6g}", "frictionloss": f"{servo.frictionloss:.6g}",
            "limited": "true"})
    ET.SubElement(body, "inertial", {
        "pos": _fmt(_link_com(link)), "mass": f"{link.mass:.6g}",
        "diaginertia": _fmt(_link_inertia(link))})
    _add_geom(body, link)

    if link_name in ("left_foot", "right_foot"):
        ET.SubElement(body, "site", {
            "name": f"{link_name}_sole", "pos": _fmt((0.012, 0.0, -spec.FOOT_HEIGHT / 2)),
            "size": "0.006", "rgba": "0 0 0 0"})

    for child_joint in _children_of(link_name):
        _build_body(body, child_joint.child, child_joint.origin, child_joint)


def _find_body(root: ET.Element, name: str) -> ET.Element:
    for body in root.iter("body"):
        if body.get("name") == name:
            return body
    raise KeyError(name)


def build_tree(with_task_objects: bool = False) -> ET.Element:
    root = ET.Element("mujoco", {"model": "microduck_fetch" if with_task_objects else "microduck"})
    ET.SubElement(root, "compiler", {"angle": "radian", "autolimits": "true"})
    ET.SubElement(root, "option", {
        "timestep": f"{spec.SIM_TIMESTEP:.6g}", "gravity": "0 0 -9.81",
        "integrator": "implicitfast", "iterations": "8", "ls_iterations": "8"})
    ET.SubElement(root, "size", {"njmax": "400", "nconmax": "150"})

    default = ET.SubElement(root, "default")
    ET.SubElement(default, "geom", {
        "condim": "3", "friction": "0.9 0.02 0.01", "density": "0",
        "solref": "0.008 1", "solimp": "0.95 0.99 0.001"})

    asset = ET.SubElement(root, "asset")
    ET.SubElement(asset, "texture", {
        "name": "sky", "type": "skybox", "builtin": "gradient",
        "rgb1": "0.55 0.72 0.90", "rgb2": "0.10 0.14 0.22",
        "width": "256", "height": "256"})
    ET.SubElement(asset, "texture", {
        "name": "grid", "type": "2d", "builtin": "checker",
        "rgb1": "0.22 0.24 0.27", "rgb2": "0.28 0.30 0.34",
        "width": "300", "height": "300"})
    ET.SubElement(asset, "material", {
        "name": "grid", "texture": "grid", "texrepeat": "8 8", "reflectance": "0.05"})

    world = ET.SubElement(root, "worldbody")
    ET.SubElement(world, "light", {"pos": "0 0 2.0", "dir": "0 0 -1", "directional": "true"})
    ET.SubElement(world, "geom", {
        "name": "floor", "type": "plane", "size": "0 0 0.05", "material": "grid",
        "contype": "1", "conaffinity": "1", "condim": "3"})

    torso = ET.SubElement(world, "body", {
        "name": "torso", "pos": _fmt((0.0, 0.0, spec.NOMINAL_STANDING_HEIGHT))})
    ET.SubElement(torso, "freejoint", {"name": "root"})
    torso_link = spec.LINK_BY_NAME["torso"]
    ET.SubElement(torso, "inertial", {
        "pos": _fmt(_link_com(torso_link)), "mass": f"{torso_link.mass:.6g}",
        "diaginertia": _fmt(_link_inertia(torso_link))})
    _add_geom(torso, torso_link)
    ET.SubElement(torso, "site", {
        "name": spec.SENSORS.imu_sites[0], "pos": "0 0 0", "size": "0.005", "rgba": "0 0 0 0"})
    for joint in _children_of("torso"):
        _build_body(torso, joint.child, joint.origin, joint)

    head_el = _find_body(root, "head")
    ET.SubElement(head_el, "site", {
        "name": spec.SENSORS.imu_sites[1], "pos": "0 0 0.01", "size": "0.004", "rgba": "0 0 0 0"})
    ET.SubElement(head_el, "camera", {
        "name": spec.SENSORS.camera_site, "pos": "0.028 0 0.012",
        "xyaxes": "0 -1 0 0 0 1", "fovy": f"{spec.SENSORS.camera_fovy:.6g}"})
    ET.SubElement(head_el, "site", {
        "name": spec.SENSORS.lidar_site, "pos": "0.028 0 -0.002",
        "size": "0.003", "rgba": "0 0 0 0"})
    # The lower jaw is rigid with the head; only the upper jaw is actuated.
    lower = spec.LINK_BY_NAME["lower_beak"]
    ET.SubElement(head_el, "geom", {
        "name": "lower_beak", "type": "box", "size": _fmt(lower.shape[1]),
        "pos": _fmt((0.022 + spec.BEAK_LENGTH / 2, 0.0, 0.004 - spec.BEAK_OPEN_GAP / 2)),
        "rgba": _fmt(lower.rgba), "contype": "1", "conaffinity": "1",
        "mass": f"{lower.mass:.6g}"})
    #: Mid-jaw point: where an object has to be for the beak to close on it.
    ET.SubElement(head_el, "site", {
        "name": "beak_grip", "size": "0.004",
        "pos": _fmt((0.022 + spec.BEAK_LENGTH, 0.0, 0.004 - spec.BEAK_OPEN_GAP / 4)),
        "rgba": "0 0 0 0"})

    if with_task_objects:
        _add_task_objects(root, world)

    _add_actuators(root)
    _add_sensors(root)
    return root


def _add_task_objects(root: ET.Element, world: ET.Element) -> None:
    """The ball to fetch and the home pad to bring it back to."""
    ball = ET.SubElement(world, "body", {"name": "ball", "pos": f"0.45 0 {BALL_RADIUS:.6g}"})
    ET.SubElement(ball, "freejoint", {"name": "ball_free"})
    ET.SubElement(ball, "geom", {
        "name": "ball", "type": "sphere", "size": f"{BALL_RADIUS:.6g}",
        "mass": f"{BALL_MASS:.6g}", "rgba": "0.85 0.25 0.30 1",
        "contype": "1", "conaffinity": "1", "condim": "4",
        "friction": "1.2 0.05 0.02", "solref": "0.006 1"})
    ET.SubElement(ball, "site", {"name": "ball_center", "size": "0.004", "rgba": "0 0 0 0"})

    # Visual-only marker for the drop-off point; it must not trip the robot.
    home = ET.SubElement(world, "body", {"name": "home_pad", "pos": "0 0 0.001"})
    ET.SubElement(home, "geom", {
        "name": "home_pad", "type": "cylinder", "size": f"{HOME_RADIUS:.6g} 0.001",
        "rgba": "0.25 0.70 0.45 0.35", "contype": "0", "conaffinity": "0"})
    ET.SubElement(home, "site", {"name": "home_center", "size": "0.004", "rgba": "0 0 0 0"})

    # Grasp constraint, inactive until the policy closes the beak on the ball.
    # See sim/fetch_env.py for why the default grasp model is a constraint
    # rather than pure friction contact.
    equality = ET.SubElement(root, "equality")
    ET.SubElement(equality, "weld", {
        "name": "beak_grasp", "body1": "head", "body2": "ball",
        "active": "false", "solref": "0.01 1", "solimp": "0.9 0.95 0.001"})


def _add_actuators(root: ET.Element) -> None:
    actuators = ET.SubElement(root, "actuator")
    for joint in spec.JOINTS:
        servo = joint.servo
        ET.SubElement(actuators, "position", {
            "name": joint.name, "joint": joint.name,
            "kp": f"{servo.kp:.6g}", "kv": f"{servo.kd:.6g}",
            "ctrlrange": _fmt(joint.range),
            "forcerange": _fmt((-servo.max_torque, servo.max_torque))})


def _add_sensors(root: ET.Element) -> None:
    sensors = ET.SubElement(root, "sensor")
    for site in spec.SENSORS.imu_sites:
        tag = site.replace("_imu", "")
        ET.SubElement(sensors, "gyro", {"name": f"{tag}_gyro", "site": site})
        ET.SubElement(sensors, "accelerometer", {"name": f"{tag}_accel", "site": site})
        ET.SubElement(sensors, "framequat", {
            "name": f"{tag}_quat", "objtype": "site", "objname": site})
    ET.SubElement(sensors, "framelinvel", {
        "name": "torso_linvel", "objtype": "site", "objname": spec.SENSORS.imu_sites[0]})
    for joint in spec.JOINTS:
        ET.SubElement(sensors, "jointpos", {"name": f"{joint.name}_pos", "joint": joint.name})
        ET.SubElement(sensors, "jointvel", {"name": f"{joint.name}_vel", "joint": joint.name})
        ET.SubElement(sensors, "actuatorfrc", {"name": f"{joint.name}_frc", "actuator": joint.name})


def to_xml(with_task_objects: bool = False) -> str:
    raw = ET.tostring(build_tree(with_task_objects), encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ")
    body = "\n".join(line for line in pretty.splitlines()[1:] if line.strip())
    return ("<!-- Generated by microduck.model.builder from spec.py. "
            "Do not edit by hand: run `microduck build-model`. -->\n" + body + "\n")


def write_all() -> list[Path]:
    MODEL_PATH.write_text(to_xml(False))
    FETCH_MODEL_PATH.write_text(to_xml(True))
    return [MODEL_PATH, FETCH_MODEL_PATH]


if __name__ == "__main__":  # pragma: no cover
    for p in write_all():
        print(p)
