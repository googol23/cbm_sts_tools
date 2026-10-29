#!/usr/bin/env python3
"""Render a CameraView JSON scene using an existing capture script backend.

For now this launcher adapts the shared CPU rasterizer in
``capture_sts_cfSupport.py``. It does not modify that source file.
"""

import argparse
import importlib.util
from pathlib import Path

from CameraView import SceneConfig


LEGACY_CAMERA_KEYS = {
    "perspective": "Perspective",
    "orthographic_zoy": "ZOY",
    "orthographic_zox": "ZOX",
    "orthographic_xoy": "XOY",
}


def load_backend(path):
    spec = importlib.util.spec_from_file_location("camera_view_capture_backend", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load capture backend: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configure_backend(backend, config):
    scene = config.data
    node_path = scene["geometry"]["node"]
    backend.PATH = tuple(part for part in node_path.split("/") if part)

    # Keep the legacy renderer's panel ordering/layout while populating each
    # camera and overlay from the JSON pad configuration.
    id_to_alias = {str(pad_id): alias for alias, pad_id in config.aliases.items()}
    cameras = {}
    dimensions = {}
    for pad_id in config.layout:
        pass
    from CameraView import PadLayout
    for pad_id in PadLayout(config.layout).indices:
        alias = id_to_alias.get(pad_id)
        legacy_key = LEGACY_CAMERA_KEYS.get(alias)
        if legacy_key is None:
            raise ValueError(f"no known legacy camera mapping for pad {pad_id!r} ({alias!r})")
        camera = config.for_pad("cameras", pad_id)
        cameras[legacy_key] = {
            "direction": tuple(camera["direction"]),
            "up": tuple(camera["up"]),
            "zoom": camera.get("zoom", 1.0),
            "perspective": camera.get("perspective", False),
        }
        definitions = config.for_pad("dimensions", pad_id)
        if definitions:
            dimensions[legacy_key] = definitions
    backend.CAMERA_VIEWS = cameras
    backend.DIMENSIONS = dimensions

    render = config.render
    style = render.get("dimension_style", {})
    backend.OUTPUT_DPI = int(render.get("dpi", [300, 300])[0])
    backend.TICK_LABEL_FONT_SIZE = render.get("typography", {}).get("tick_label_font_size", 20)
    backend.PAD_TITLE_FONT_SIZE = render.get("typography", {}).get("pad_title_font_size", 26)
    backend.AXIS_TITLE_FONT_SIZE = render.get("typography", {}).get("axis_title_font_size", 16)
    backend.DIMENSION_FONT_SIZE = style.get("font_size", 18)
    backend.DIMENSION_COLOR = tuple(style.get("color_rgb", [165, 45, 40]))
    backend.DIMENSION_LINE_WIDTH = style.get("line_width", 2)
    backend.DIMENSION_OFFSET_PX = style.get("default_offset_px", 48)
    backend.DIMENSION_EXTENSION_DASH_PX = tuple(style.get("extension_dash_px", [3, 5]))
    backend.DIMENSION_EXTENSION_WIDTH = style.get("extension_width", 2)
    backend.DIMENSION_EXTENSION_OVERHANG_PX = style.get("extension_overhang_px", 12)
    backend.DIMENSION_ARROW_LENGTH_PX = style.get("arrow_length_px", 9)
    backend.DIMENSION_ARROW_HALF_WIDTH_PX = style.get("arrow_half_width_px", 5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    here = Path(__file__).resolve().parent
    parser.add_argument(
        "config", nargs="?",
        default=str(here / "CameraView" / "capture_sts_cfSupport.json"),
        help="CameraView JSON/YAML scene file",
    )
    parser.add_argument(
        "--backend", default=str(here / "capture_sts_cfSupport.py"),
        help="unchanged capture script used as the rasterization backend",
    )
    parser.add_argument("