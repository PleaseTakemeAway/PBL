"""Legacy DXF loader: views come from explicitly named FRONT/TOP/RIGHT layers."""

from pathlib import Path

from cutplan_agent.reconstruct.models import DrawingDocument


def load_dxf_by_layers(path: Path) -> DrawingDocument:
    try:
        import ezdxf
    except ImportError as exc:
        raise RuntimeError(
            "DXF input requires ezdxf: pip install -r requirements.txt"
        ) from exc
    document = ezdxf.readfile(path)
    groups = {}
    unsupported = []
    names = {"FRONT": "front", "TOP": "top", "RIGHT": "right"}
    for entity in document.modelspace():
        layer = entity.dxf.layer.upper()
        if layer not in names:
            continue
        group = groups.setdefault(
            layer,
            {"id": layer, "name": names[layer], "primitives": [], "annotations": []},
        )
        kind, eid = entity.dxftype(), entity.dxf.handle
        linetype = entity.dxf.linetype
        if linetype.upper() == "BYLAYER":
            linetype = document.layers.get(entity.dxf.layer).dxf.linetype
        attrs = {"layer": layer, "linetype": linetype}
        if kind == "LINE":
            if abs(entity.dxf.start.z) > 1e-9 or abs(entity.dxf.end.z) > 1e-9:
                raise ValueError("DXF views must be planar in the XY drawing plane")
            group["primitives"].append(
                {
                    "id": eid,
                    "kind": "line",
                    "points": [tuple(entity.dxf.start)[:2], tuple(entity.dxf.end)[:2]],
                    "attributes": attrs,
                }
            )
        elif kind in {"CIRCLE", "LWPOLYLINE"}:
            if tuple(entity.dxf.extrusion) != (0.0, 0.0, 1.0):
                raise ValueError(
                    "DXF OCS transforms are not supported; flatten the view first"
                )
            if kind == "CIRCLE":
                if abs(entity.dxf.center.z) > 1e-9:
                    raise ValueError("DXF circle elevation must be zero")
                group["primitives"].append(
                    {
                        "id": eid,
                        "kind": "circle",
                        "center": tuple(entity.dxf.center)[:2],
                        "radius": entity.dxf.radius,
                        "attributes": attrs,
                    }
                )
            else:
                if abs(entity.dxf.elevation) > 1e-9:
                    raise ValueError("DXF polyline elevation must be zero")
                points = entity.get_points("xyb")
                if any(abs(p[2]) > 1e-12 for p in points):
                    unsupported.append(
                        {"entity": eid, "kind": "bulged LWPOLYLINE", "view": layer}
                    )
                    continue
                pairs = list(zip(points, points[1:]))
                if entity.closed and len(points) > 1:
                    pairs.append((points[-1], points[0]))
                for i, (a, b) in enumerate(pairs):
                    group["primitives"].append(
                        {
                            "id": f"{eid}:{i}",
                            "kind": "line",
                            "points": [a[:2], b[:2]],
                            "attributes": attrs,
                        }
                    )
        elif kind in {"TEXT", "MTEXT"}:
            text = entity.dxf.text if kind == "TEXT" else entity.plain_text()
            group["annotations"].append(
                {
                    "id": eid,
                    "kind": "text",
                    "text": text,
                    "position": tuple(entity.dxf.insert)[:2],
                }
            )
        else:
            unsupported.append({"entity": eid, "kind": kind, "view": layer})
    units = {1: "inch", 4: "mm", 5: "cm", 6: "m"}.get(
        document.header.get("$INSUNITS", 0)
    )
    return DrawingDocument.from_dict(
        {
            "metadata": {"units": units, "unsupported_entities": unsupported},
            "views": list(groups.values()),
        },
        str(path),
    )
