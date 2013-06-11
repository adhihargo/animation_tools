# Author: Adhi Hargo (cadmus.sw@gmail.com)
# License: GPL v2

import bpy, os
from mathutils import Matrix, Vector
from bpy.app.handlers import persistent
from bl_operators.presets import AddPresetBase, ExecutePreset

bl_info = {
    "name": "OHA Animation Tools",
    "author": "Adhi Hargo",
    "version": (2013, 5, 6),
    "blender": (2, 67, 0),
    "location": "F-Curve Editor > Tools",
    "description": "Various animation tools.",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Animation"}

def get_pbone_parent_matrix(pbone):
    # like parent_recursive, but tries to detect active
    # Child Of constraint and get its target instead.
    parent = matrix = inv_matrix = None
    if pbone.constraints != None:
        co = [c for c in pbone.constraints
              if c.type == 'CHILD_OF' and c.influence == 1.0]
        if co:
            co = co[0]                
            parent = co.target
            matrix = parent.matrix_basis.inverted()
            inv_matrix = co.inverse_matrix

            if not parent:
                parent = pbone.parent
                if parent:
                    matrix = parent.matrix_basis

    return parent, matrix, inv_matrix

def bake_action(obj, frame_start, frame_end, only_selected, only_visible):
    action = obj.animation_data.action

    bones = [b for b in obj.data.bones if b.select] if only_selected else []

    for fcurve in action.fcurves:
        if only_visible and fcurve.hide:
            continue
        if only_selected and\
                not True in map(lambda bone: bone.name in fcurve.data_path,
                                bones):
            continue

        if len(fcurve.modifiers) == 1 and fcurve.modifiers[0].type == 'CYCLES':
            cm = fcurve.modifiers[0]

            key_min = min(fcurve.keyframe_points, key=lambda x: x.co.x)
            key_max = max(fcurve.keyframe_points, key=lambda x: x.co.x)
            key_min.handle_right_type = key_max.handle_left_type = 'FREE'
            key_min.handle_left_type = key_max.handle_right_type = 'VECTOR'
            key_delta = key_max.co - key_min.co
            key_delta.x += 1

            # These always return False if cycle count is set to 0
            # (which means infinite cycle).
            check_cycles_before = \
                lambda c: False if cm.cycles_before == 0 else\
                lambda c: c > cm.cycles_before
            check_cycles_after = \
                lambda c: False if cm.cycles_after == 0 else\
                lambda c: c > cm.cycles_after

            for key in fcurve.keyframe_points:
                # Extend before original cycle
                count = 0
                key_delta_before = key_delta
                if cm.mode_before != 'REPEAT_OFFSET':
                    key_delta_before.y = 0
                while True:
                    count += 1

                    key_offset = -(count * key_delta_before)
                    key_new = fcurve.keyframe_points.insert(
                        key.co.x+key_offset.x, key.co.y+key_offset.y)
                    key_new.handle_left_type = key.handle_left_type
                    key_new.handle_right_type = key.handle_right_type
                    key_new.handle_left = key.handle_left + key_offset
                    key_new.handle_right = key.handle_right + key_offset

                    if check_cycles_before(count) or\
                            (key.co.x+key_offset.x) <= frame_start:
                        break

                # Extend after original cycle
                count = 0
                key_delta_after = key_delta
                if cm.mode_after != 'REPEAT_OFFSET':
                    key_delta_after.y = 0
                while True:
                    count += 1

                    key_offset = count * key_delta_after
                    key_new = fcurve.keyframe_points.insert(
                        key.co.x+key_offset.x, key.co.y+key_offset.y)
                    key_new.handle_left_type = key.handle_left_type
                    key_new.handle_right_type = key.handle_right_type
                    key_new.handle_left = key.handle_left + key_offset
                    key_new.handle_right = key.handle_right + key_offset

                    if check_cycles_after(count) or\
                            (key.co.x+key_offset.x) >= frame_end:
                        break

            fcurve.modifiers.remove(cm)
        else:
            continue

    return action

# ======================================================================
# ============================== Operators =============================
# ======================================================================

# Uses bpy.ops.nla.bake as starting point.
class oha_FCurveBakeAction(bpy.types.Operator):
    """Bake object/pose loc/scale/rotation animation to a new action"""
    bl_idname = 'graph.oha_fcurve_bake_action'
    bl_label = 'Bake Action'
    bl_options = {'REGISTER', 'UNDO'}

    frame_start = bpy.props.IntProperty(
        name="Start Frame",
        description="Start frame for baking",
        min=0, max=300000,
        default=1,
        )

    frame_end = bpy.props.IntProperty(
        name="End Frame",
        description="End frame for baking",
        min=1, max=300000,
        default=250,
        )

    only_selected = bpy.props.BoolProperty(
        name="Only Selected",
        description="Only key selected bones",
        default=True,
        )

    only_visible = bpy.props.BoolProperty(
        name="Only Visible",
        description="Only key visible f-curve channels",
        default=False,
        )

    @classmethod
    def poll(self, context):
        return context.active_object != None\
            and context.active_object.animation_data != None

    def execute(self, context):
        obj = context.active_object
        action = bake_action(obj,
                             self.frame_start,
                             self.frame_end,
                             only_selected=self.only_selected\
                                 if obj.type == 'ARMATURE'\
                                 else False,
                             only_visible=self.only_visible)

        if action is None:
            self.report({'INFO'}, "Nothing to bake")
            return {'CANCELLED'}

        context.area.tag_redraw()
        return {'FINISHED'}

    def invoke(self, context, event):
        self.frame_start = context.scene.frame_start
        self.frame_end = context.scene.frame_end
    
        return context.window_manager.invoke_props_dialog(self)

class oha_FCurveAddCycleModifierToAllChannels(bpy.types.Operator):
    """Add cycle modifier to all available f-curve channels"""
    bl_idname = 'graph.oha_fcurve_add_cycle_modifier'
    bl_label = 'Add Cycle Modifier'
    bl_options = {'REGISTER', 'UNDO'}

    cycles_before = bpy.props.IntProperty(
        name = 'Cycles Before')

    cycles_after = bpy.props.IntProperty(
        name = 'Cycles After')

    mode_before = bpy.props.EnumProperty(
        name = 'Mode Before',
        items = [('NONE', 'No Cycles', ''),
                 ('REPEAT', 'Repeat Motion', ''),
                 ('REPEAT_OFFSET', 'Repeat with Offset', ''),
                 ('MIRROR', 'Repeat Mirrored', ''),
                 ],
        default = 'REPEAT_OFFSET')

    mode_after = bpy.props.EnumProperty(
        name = 'Mode After',
        items = [('NONE', 'No Cycles', ''),
                 ('REPEAT', 'Repeat Motion', ''),
                 ('REPEAT_OFFSET', 'Repeat with Offset', ''),
                 ('MIRROR', 'Repeat Mirrored', ''),
                 ],
        default = 'REPEAT_OFFSET')

    only_selected = bpy.props.BoolProperty(
        name="Only Selected",
        description="Only key selected bones",
        default=True,
        )

    only_visible = bpy.props.BoolProperty(
        name="Only Visible",
        description="Only key visible f-curve channels",
        default=False,
        )

    @classmethod
    def poll(self, context):
        return context.active_object != None\
            and context.active_object.animation_data != None\
            and context.active_object.animation_data.action != None

    def draw(self, context):
        layout = self.layout
        row = layout.row()

        col = row.column(align=True)
        col.prop(self, 'mode_before', text='')
        col.prop(self, 'cycles_before')

        col = row.column(align=True)
        col.prop(self, 'mode_after', text='')
        col.prop(self, 'cycles_after')

        row = layout.row()
        row.prop(self, 'only_selected')
        row.prop(self, 'only_visible')

    def execute(self, context):
        obj = context.active_object
        bones = [b for b in obj.data.bones if b.select]\
            if obj.type == 'ARMATURE' and self.only_selected \
            else []

        for fcurve in obj.animation_data.action.fcurves:
            if self.only_visible and fcurve.hide:
                continue
            if self.only_selected and\
                    obj.type == 'ARMATURE' and\
                    not True in map(lambda bone: bone.name in fcurve.data_path,\
                                        bones):
                continue

            cm = None
            for m in fcurve.modifiers:
                if m.type == 'CYCLES':
                    cm = m
                    break
            if not cm:
                cm = fcurve.modifiers.new(type = 'CYCLES')
            cm.mode_before = self.mode_before
            cm.mode_after = self.mode_after
            cm.cycles_before = self.cycles_before
            cm.cycles_after = self.cycles_after

        context.area.tag_redraw()
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

class GRAPH_OT_oha_FCurveRemoveCycleModifierToAllChannels(bpy.types.Operator):
    """Removes cycle modifier from all available f-curve channels"""
    bl_idname = 'graph.oha_fcurve_remove_cycle_modifier'
    bl_label = 'Remove Cycle Modifier'
    bl_options = {'REGISTER', 'UNDO'}

    only_selected = bpy.props.BoolProperty(
        name="Only Selected",
        description="Only key selected bones",
        default=True,
        )

    only_visible = bpy.props.BoolProperty(
        name="Only Visible",
        description="Only key visible f-curve channels",
        default=False,
        )

    @classmethod
    def poll(self, context):
        return context.active_object != None\
            and context.active_object.animation_data != None\
            and context.active_object.animation_data.action != None

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        row.prop(self, "only_selected")
        row.prop(self, "only_visible")

    def execute(self, context):
        obj = context.active_object
        bones = [b for b in obj.data.bones if b.select]\
            if obj.type == 'ARMATURE' and self.only_selected \
            else []

        for fcurve in obj.animation_data.action.fcurves:
            if self.only_visible and fcurve.hide:
                continue
            if self.only_selected and\
                    obj.type == 'ARMATURE' and\
                    not True in map(lambda bone: bone.name in fcurve.data_path,\
                                        bones):
                continue            

            for m in fcurve.modifiers:
                if m.type == 'CYCLES':
                    fcurve.modifiers.remove(m)

        context.area.tag_redraw()
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

class VIEW3D_OT_oha_ObjectSnapToPrevKeyframe(bpy.types.Operator):
    """Snap active object/bone to selected object."""
    bl_idname = 'object.oha_snap_to_prev_keyframe'
    bl_label = 'Snap to Previous Keyframe'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(self, context):
        return context.active_object != None\
            and context.active_object.animation_data != None\
            and context.active_object.animation_data.action != None

    def execute(self, context):
        bone = context.active_pose_bone
        action = context.object.animation_data.action
        fcurves = [str(c) for c in action.fcurves if bone.name in c.data_path]
        print("\n".join(fcurves))
        print('*' * 50)
        return {'FINISHED'}

class VIEW3D_OT_oha_ObjectSnapToObject(bpy.types.Operator):
    """Snap active object/bone to selected object/bone."""
    bl_idname = 'object.oha_snap_to_object'
    bl_label = 'Snap to Object'
    bl_options = {'REGISTER', 'UNDO'}

    snap_rotation = bpy.props.BoolProperty(
        name="Rotation",
        description="Also adjusting rotation to reference object.",
        default=True,
        )

    snap_scale = bpy.props.BoolProperty(
        name="Scale",
        description="Also adjusting scale to reference object.",
        default=False,
        )

    snap_pbone_rotation_scale = bpy.props.BoolProperty(
        name="Rotation + Scale",
        description="Also adjusting rotation and scale to reference object.",
        default=False,
        )

    @classmethod
    def poll(self, context):
        return len(context.selected_objects) == 2\
            and context.mode in ['POSE', 'OBJECT']

    def draw(self, context):
        layout = self.layout

        row = layout.row(align=True)
        if context.mode != 'POSE':
            row.prop(self, "snap_rotation", toggle=True)
            row.prop(self, "snap_scale", toggle=True)
        else:
            row.prop(self, "snap_pbone_rotation_scale", toggle=True)

    def execute(self, context):
        target = [o for o in context.selected_objects
                  if o != context.active_object][0]
        active = context.active_object

        mat = target.matrix_world
        if context.mode == 'POSE':
            # l2w = lObjw * (l2l * l1b * l0b)
            # l2l = (l2w * lObjw.inv) * l1b.inv * l0b.inv
            # mat = active.matrix_world.inverted() * mat

            if self.snap_pbone_rotation_scale:
                pbone = context.active_pose_bone
                for p in pbone.parent_recursive:
                    mat = p.matrix_basis * mat
                mat[3][0] = mat[3][1] = mat[3][2] = 0
                pbone.matrix = mat

            cursor_old = context.scene.cursor_location.copy()
            
            context.scene.objects.active = target
            bpy.ops.view3d.snap_cursor_to_active()

            context.scene.objects.active = active
            bpy.ops.view3d.snap_selected_to_cursor()

            context.scene.cursor_location = cursor_old

        elif target.type == 'ARMATURE' and target.data.bones.active != None:
            target_bone = target.pose.bones.get(target.data.bones.active.name)
            
            mat = target.matrix_world * target_bone.matrix
            active.location = mat.to_translation()

            if self.snap_rotation:
                active.rotation_mode = 'XYZ'
                active.rotation_euler = mat.to_euler()

            if self.snap_scale:
                scl = mat.to_scale()
                scl_avg = (scl[0] + scl[1] + scl[2]) / 3
                active.scale = ((target_bone.length * scl_avg),
                                (target_bone.length * scl_avg),
                                (target_bone.length * scl_avg))

        else:
            rot_orig = active.matrix_world.to_euler()
            scl_orig = active.matrix_world.to_scale()
            active.matrix_world = target.matrix_world
            if not self.snap_rotation:
                active.rotation_mode = 'XYZ'
                active.rotation_euler = rot_orig
            if not self.snap_scale: active.scale = scl_orig

        return {'FINISHED'}

class SEQUENCER_OT_oha_MovieStripAdd(bpy.types.Operator):
    """Add one or more movie strips, each file's audio and video strips automatically grouped as one metastrip."""
    bl_idname = 'sequencer.oha_grouped_movie_strip_add'
    bl_label = 'Add Grouped Movie Strips'
    bl_options = {'REGISTER', 'UNDO'}

    files = bpy.props.CollectionProperty(
        name="File Path",
        type=bpy.types.OperatorFileListElement)
    directory = bpy.props.StringProperty(
        default='//', subtype='DIR_PATH',
        options={'HIDDEN'})

    frame_start = bpy.props.IntProperty(
        subtype='UNSIGNED',
        options={'HIDDEN'})
    filter_movie = bpy.props.BoolProperty(
        default=True,
        options={'HIDDEN'})
    filter_folder = bpy.props.BoolProperty(
        default=True,
        options={'HIDDEN'})

    channel = bpy.props.IntProperty(
        name='Channel',
        default=1,
        min=1,max=32)
    consecutive = bpy.props.BoolProperty(
        name='Consecutive Strips',
        description='Position all movie strips in the same channel, one after the other.',
        default=True
        )

    def execute(self, context):
        frame_start = self.frame_start
        channel = self.channel

        for f in self.files:
            if f.name == '': continue

            filepath = os.path.join(self.directory, f.name)
            bpy.ops.sequencer.movie_strip_add(
                filepath = filepath,
                frame_start = frame_start,
                channel = channel)
            bpy.ops.sequencer.meta_make()
            active_strip = context.scene.sequence_editor.active_strip
            active_strip.name = '%.50s_group' % f.name
            if self.consecutive:
                frame_start = active_strip.frame_final_end
        return {'FINISHED'}

    def invoke(self, context, event):
        self.frame_start = context.scene.frame_start
    
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class RENDER_OT_oha_validate_and_render(bpy.types.Operator):
    """Check and modify all render-related scene settings before rendering."""
    bl_idname = 'render.oha_validate_and_render'
    bl_label = 'Animation (QC)'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.oha_animtool_props
        filepath = props.render_preset_filepath
        menu_idname = props.render_preset_menu_idname
        if filepath != '':
            bpy.ops.script.oha_execute_preset(filepath=filepath,
                                              menu_idname=menu_idname)
        bpy.ops.render.render('INVOKE_DEFAULT', animation=True)
        return {'FINISHED'}

class RENDER_OT_oha_render_qc_preset_add(AddPresetBase, bpy.types.Operator):
    """Add a new preset containing all indicated settings."""
    bl_idname = 'render.oha_render_qc_preset_add'
    bl_label = 'Add Render QC Preset'
    bl_options = {'REGISTER', 'UNDO'}
    preset_menu = 'RENDER_MT_qc_presets'
    preset_subdir = 'render_qc'

    preset_defines = [
        "scene  = bpy.context.scene",
        "render = bpy.context.scene.render",
        "image  = bpy.context.scene.render.image_settings",
        "ffmpeg = bpy.context.scene.render.ffmpeg"
        ]

    preset_values = [
        "scene.use_preview_range",
        "render.engine",
        "render.use_stamp",                     "render.use_stamp_marker",
        "render.use_stamp_camera",              "render.use_stamp_note",
        "render.use_stamp_date",                "render.use_stamp_render_time",
        "render.use_stamp_filename",            "render.use_stamp_scene",
        "render.use_stamp_frame",               "render.use_stamp_sequencer_strip",
        "render.use_stamp_lens",                "render.use_stamp_time",        
        "render.use_simplify",                  "render.use_antialiasing",
        "render.use_freestyle",
        "render.stamp_note_text",               "render.resolution_percentage",
        "render.stamp_background",              "render.resolution_x",         
        "render.stamp_font_size",               "render.resolution_y",
        "render.filepath",
        "image.file_format",                    "ffmpeg.format",
        "ffmpeg.codec",                         "ffmpeg.audio_codec",
        "ffmpeg.video_bitrate",                 "ffmpeg.audio_bitrate",        
        "ffmpeg.audio_channels",
        ]

    @staticmethod
    def as_filename(name):  # could reuse for other presets
        for char in " !@#$%^&*(){}:\";'[]<>,.\\/?":
            name = name.replace(char, '_')
        return name.strip()

class SCRIPT_OT_oha_execute_preset(ExecutePreset):
    """Execute a preset"""
    bl_idname = "script.oha_execute_preset"
    bl_label = "Execute a Python Preset"

    filepath = ExecutePreset.filepath
    menu_idname = ExecutePreset.menu_idname

    def execute(self, context):
        props = context.scene.oha_animtool_props
        props.render_preset_filepath = self.filepath
        props.render_preset_menu_idname = self.menu_idname
        return ExecutePreset.execute(self, context)

# ======================================================================
# =========================== User Interface ===========================
# ======================================================================

class RENDER_MT_qc_presets(bpy.types.Menu):
    bl_label = "Presets"
    preset_subdir = "render_qc"
    preset_operator = "script.oha_execute_preset"
    
    # Minimally modified from scripts/modules/bpy_types.py
    def path_menu(self, searchpaths, operator,
                  props_default={}, filter_ext=None):

        layout = self.layout
        # hard coded to set the operators 'filepath' to the filename.

        import os
        import bpy.utils

        layout = self.layout

        if not searchpaths:
            layout.label("* Missing Paths *")

        # collect paths
        files = []
        for directory in searchpaths:
            files.extend([(f, os.path.join(directory, f))
                          for f in os.listdir(directory)
                          if (not f.startswith("."))
                          if ((filter_ext is None) or
                              (filter_ext(os.path.splitext(f)[1])))
                          ])

        files.sort()

        for f, filepath in files:
            props = layout.operator(operator,
                                    text=bpy.path.display_name(f),
                                    translate=False)

            for attr, value in props_default.items():
                setattr(props, attr, value)

            props.filepath = filepath
            props.menu_idname = self.bl_idname

    def draw(self, context):
        bpy.types.Menu.draw_preset(self, context)

class RENDER_PT_oha_RenderQCPanel(bpy.types.Panel):
    bl_label = 'OHA Render QC'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'render'

    def draw(self, context):
        layout = self.layout

        row = layout.row(align=True)
        row.menu("RENDER_MT_qc_presets",
                 text=bpy.types.RENDER_MT_qc_presets.bl_label)
        row.operator("render.oha_render_qc_preset_add", text="", icon='ZOOMIN')
        row.operator("render.oha_render_qc_preset_add", text="", icon='ZOOMOUT').remove_active = True

class GRAPH_PT_oha_AnimationToolsFCurvePanel(bpy.types.Panel):
    bl_label = 'OHA Animation Tools'
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'

    @classmethod
    def poll(self, context):
        return context.active_object != None\
            and context.active_object.animation_data != None

    def draw(self, context):
        layout = self.layout

        row = layout.row(align=True)
        row.operator('graph.oha_fcurve_add_cycle_modifier')
        row.operator('graph.oha_fcurve_remove_cycle_modifier', icon="CANCEL",
                     text='')

        row = layout.row(align=True)
        row.operator('graph.oha_fcurve_bake_action')

class VIEW3D_PT_oha_AnimationToolsPanel(bpy.types.Panel):
    bl_label = 'OHA Animation Tools'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    @classmethod
    def poll(self, context):
        return True

    def draw(self, context):
        layout = self.layout

        row = layout.row(align=True)
        row.prop(context.scene.tool_settings, "use_keyframe_insert_auto",
                 text='')
        row.prop_search(context.scene.keying_sets_all, "active",
                        context.scene, "keying_sets_all", text='')

        col = layout.column(align=True)
        col.operator('object.oha_snap_to_object')

class SEQUENCER_PT_oha_AnimationToolsPanel(bpy.types.Panel):
    bl_label = 'OHA Animation Tools'
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'

    @classmethod
    def poll(self, context):
        return True

    def draw(self, context):
        layout = self.layout

        col = layout.column(align=True)
        col.operator('sequencer.oha_grouped_movie_strip_add')

class OHA_AnimationToolProps(bpy.types.PropertyGroup):
    render_preset_filepath = bpy.props.StringProperty(
        subtype='FILE_PATH', options={'SKIP_SAVE'})
    render_preset_menu_idname = bpy.props.StringProperty(
        options={'SKIP_SAVE'})

def qc_render_properties(self, context):
    layout = self.layout

    row = layout.row(align=True)
    row.operator('render.oha_validate_and_render', icon='RENDER_ANIMATION')

def register():
    bpy.utils.register_module(__name__)
    bpy.types.RENDER_PT_render.prepend(qc_render_properties)
    bpy.types.Scene.oha_animtool_props = bpy.props.PointerProperty(
        type = OHA_AnimationToolProps,
        options = {'HIDDEN'})

def unregister():
    bpy.utils.unregister_module(__name__)
    bpy.types.RENDER_PT_render.remove(qc_render_properties)
    del bpy.types.Scene.oha_animtool_props

if __name__ == "__main__":
    register()
