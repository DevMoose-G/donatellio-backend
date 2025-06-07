# blender_render.py

import os
import sys

import bpy
import mathutils

# 2. Clear default scene
bpy.ops.wm.read_factory_settings(use_empty=True)


def get_world_bbox(obj):
    """Return (world_min, world_max) for obj (axis-aligned)."""
    # Ensure the object’s world matrices are up to date
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)

    # Access the evaluated mesh if modifiers exist:
    mesh = eval_obj.to_mesh()
    coords = [eval_obj.matrix_world @ v.co for v in mesh.vertices]

    # Compute min/max across all vertices
    world_coords = coords  # a list of Vector objects
    min_corner = mathutils.Vector(
        (
            min(v.x for v in world_coords),
            min(v.y for v in world_coords),
            min(v.z for v in world_coords),
        )
    )
    max_corner = mathutils.Vector(
        (
            max(v.x for v in world_coords),
            max(v.y for v in world_coords),
            max(v.z for v in world_coords),
        )
    )

    # Cleanup
    eval_obj.to_mesh_clear()

    return min_corner, max_corner


def render(is_textured, input_path, output_path):
    # 3. Import mesh
    bpy.ops.import_scene.gltf(filepath=input_path)

    # 4. Get reference to imported object
    obj = bpy.context.selected_objects[0]
    bb = get_world_bbox(obj.children[0])
    print(bb)
    print(bb[0].y)

    y_offset = bb[0].y
    x_width = max(abs(bb[0].x), abs(bb[1].x))
    z_height = max(abs(bb[0].z), abs(bb[1].z))

    # 5. If untextured: override materials
    if not is_textured:
        for slot in obj.material_slots:
            mat = bpy.data.materials.new(name="Clay")
            mat.diffuse_color = (0.5, 0.5, 0.5, 1)
            slot.material = mat

    # 6. Set up camera
    cam_data = bpy.data.cameras.new(name="Camera")
    cam = bpy.data.objects.new("Camera", cam_data)
    bpy.context.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    y_position = (-1 * (1.2 * (max(x_width, z_height * 1.25) * 2))) + y_offset
    cam.location = (0, y_position, 0)
    cam.rotation_euler = (1.57, 0, 0)  # approx looking at origin

    # 7. Set up lighting
    light_data = bpy.data.lights.new(name="KeyLight", type="SUN")
    light_data.energy = 3

    # In front of and to the side of the subject (usually ~45° to the right or left, and slightly above)
    light = bpy.data.objects.new(name="KeyLight", object_data=light_data)
    light.rotation_euler = (1.4, 0, -1.57 / 2)
    bpy.context.collection.objects.link(light)

    # Opposite side of the key light, also at ~45°, but lower intensity
    fill_light_data = bpy.data.lights.new(name="FillLight", type="SUN")
    fill_light_data.energy = 1
    fill_light = bpy.data.objects.new(name="FillLight", object_data=fill_light_data)
    fill_light.rotation_euler = (1.7, 0, 1.57 / 2)
    bpy.context.collection.objects.link(fill_light)

    # # Behind the subject, often above and pointing toward the back edge
    back_light_data = bpy.data.lights.new(name="BackLight", type="SUN")
    back_light_data.energy = 1
    back_light = bpy.data.objects.new(name="BackLight", object_data=back_light_data)
    back_light.rotation_euler = (1.25, 0, 1.57 + (1.2 / 2))
    bpy.context.collection.objects.link(back_light)

    # 8. Render settings
    bpy.context.scene.render.engine = "BLENDER_EEVEE_NEXT"  # or 'CYCLES'
    bpy.context.scene.render.filepath = output_path
    bpy.context.scene.render.image_settings.file_format = "PNG"
    bpy.context.scene.render.image_settings.color_mode = "RGBA"
    bpy.context.scene.render.film_transparent = True
    bpy.context.scene.render.resolution_x = 512
    bpy.context.scene.render.resolution_y = 512

    # 9. Render
    bpy.ops.render.render(write_still=True)
    print(f"PNG: {output_path}")


def main():
    """Parse arguments --import GLB, export in multiple formats, then exit."""
    argv = sys.argv
    # Everything after "--" in the invocation is ours:
    if "--" not in argv:
        print(
            "Usage: blender --background --python render.py -- <glb_path> <out_dir> <clear_texture>"
        )
        return

    args = argv[argv.index("--") + 1 :]
    if len(args) != 3:
        print("Expected exactly 2 arguments: <glb_path> <out_dir> <clear_texture>")
        return

    glb_path, out_dir, clear_texture = args
    glb_path = os.path.abspath(glb_path)
    out_dir = os.path.abspath(out_dir)
    if clear_texture == "true":
        is_textured = False
    else:
        is_textured = True

    # Ensure output directory exists:
    os.makedirs(out_dir, exist_ok=True)

    render(is_textured, glb_path, os.path.join(out_dir, "render.png"))


if __name__ == "__main__":
    main()
