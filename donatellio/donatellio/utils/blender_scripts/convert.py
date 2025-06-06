import bpy
import os
import sys

def import_glb(glb_path: str):
    """Import a GLB file into the current Blender scene (cleared)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)  # start with an empty scene :contentReference[oaicite:4]{index=4}
    bpy.ops.import_scene.gltf(filepath=glb_path)      # import the GLB :contentReference[oaicite:5]{index=5}
    return bpy.context.selected_objects                # return imported objects

def export_to_obj(output_path: str):
    """Export selected mesh objects to OBJ."""
    bpy.ops.wm.obj_export(
        filepath=output_path,
        forward_axis='NEGATIVE_Z',
        up_axis='Y',
        export_selected_objects=True
    )  # :contentReference[oaicite:6]{index=6}

def export_to_fbx(output_path: str):
    """Export selected mesh (and armature) objects to FBX."""
    bpy.ops.export_scene.fbx(
        filepath=output_path,
        use_selection=True,
        axis_forward='-Z',
        axis_up='Y',
        use_mesh_modifiers=True,
        mesh_smooth_type='FACE',
        bake_space_transform=True
    )  # :contentReference[oaicite:7]{index=7}

def export_to_stl(output_path: str):
    """Export selected mesh objects to STL (supports Blender ≥4.2 and legacy)."""
    try:
        # Blender 4.2+ :contentReference[oaicite:8]{index=8}
        bpy.ops.wm.stl_export(
            filepath=output_path,
            export_selected_objects=True,
            global_scale=1.0,
            use_scene_unit=True,
            forward_axis='NEGATIVE_Y',
            up_axis='Z'
        )
    except AttributeError:
        # Legacy (Blender 2.80–4.1) :contentReference[oaicite:9]{index=9}
        bpy.ops.export_mesh.stl(
            filepath=output_path,
            use_selection=True,
            global_scale=1.0,
            use_scene_unit=True,
            ascii=False,
            axis_forward='-Y',
            axis_up='Z'
        )

def main():
    """Parse arguments --import GLB, export in multiple formats, then exit."""
    argv = sys.argv
    # Everything after "--" in the invocation is ours:
    if "--" not in argv:
        print("Usage: blender --background --python convert_script.py -- <glb_path> <out_dir>")
        return

    args = argv[argv.index("--") + 1:]
    if len(args) != 2:
        print("Expected exactly 2 arguments: <glb_path> <out_dir>")
        return

    glb_path, out_dir = args
    glb_path = os.path.abspath(glb_path)
    out_dir = os.path.abspath(out_dir)

    # Ensure output directory exists:
    os.makedirs(out_dir, exist_ok=True)

    # 1. Import the GLB
    imported_objects = import_glb(glb_path)

    # 2. Select only meshes for export
    for obj in bpy.context.scene.objects:
        obj.select_set(obj.type == 'MESH')

    # 3. Build output filenames
    base_name = os.path.splitext(os.path.basename(glb_path))[0]
    obj_path = os.path.join(out_dir, f"export.obj")
    fbx_path = os.path.join(out_dir, f"export.fbx")
    stl_path = os.path.join(out_dir, f"export.stl")
    blend_path = os.path.join(out_dir, f"export.blend")

    # 4. Export in all formats
    export_to_obj(obj_path)
    export_to_fbx(fbx_path)
    export_to_stl(stl_path)
    bpy.ops.wm.save_mainfile(filepath=blend_path)  # save as .blend :contentReference[oaicite:10]{index=10}

    print("Export complete:")
    print(f"  OBJ:   {obj_path}")
    print(f"  FBX:   {fbx_path}")
    print(f"  STL:   {stl_path}")
    print(f"  Blend: {blend_path}")

if __name__ == "__main__":
    main()
