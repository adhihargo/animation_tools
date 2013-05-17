# Author: Adhi Hargo (cadmus.sw@gmail.com)
# License: GPL v2

import bpy
from mathutils import Matrix, Vector

bl_info = {
    "name": "ADH Animation Tools",
    "author": "Adhi Hargo",
    "version": (2013, 4, 15),
    "blender": (2, 65, 0),
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
                not True in map(lambda bone: bone.name in fcurve.data_path, bones):
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
                    key_new = fcurve.keyframe_points.insert(key.co.x+key_offset.x,
                                                            key.co.y+key_offset.y)
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
                    key_new = fcurve.keyframe_points.insert(key.co.x+key_offset.x,
                                                            key.co.y+key_offset.y)
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
class ADH_FCurveBakeAction(bpy.types.Operator):
    """Bake object/pose loc/scale/rotation animation to a new action"""
    bl_idname = 'graph.adh_fcurve_bake_action'
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

class ADH_FCurveAddCycleModifierToAllChannels(bpy.types.Operator):
    """Add cycle modifier to all available f-curve channels"""
    bl_idname = 'graph.adh_fcurve_add_cycle_modifier'
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

class GRAPH_OT_ADH_FCurveRemoveCycleModifierToAllChannels(bpy.types.Operator):
    """Removes cycle modifier from all available f-curve channels"""
    bl_idname = 'graph.adh_fcurve_remove_cycle_modifier'
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

class VIEW3D_OT_ADH_ObjectSnapToPrevKeyframe(bpy.types.Operator):
    """Snap active object/bone to selected object."""
    bl_idname = 'object.adh_snap_to_prev_keyframe'
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

class VIEW3D_OT_ADH_ObjectSnapToObject(bpy.types.Operator):
    """Snap active object/bone to selected object/bone."""
    bl_idname = 'object.adh_snap_to_object'
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

class SEQUENCER_OT_ADH_MovieStripAdd(bpy.types.Operator):
    """Snap active object/bone to selected object."""
    bl_idname = 'sequencer.adh_grouped_movie_strip_add'
    bl_label = 'Add Grouped Movie Strip'
    bl_options = {'REGISTER', 'UNDO'}

    filepath = bpy.props.StringProperty(subtype='FILE_PATH')
    # files = bpy.props.CollectionProperty()

    filter_movie = bpy.props.BoolProperty()
    frame_start = bpy.props.IntProperty(subtype='UNSIGNED')
    display_type = bpy.props.StringProperty()

    def execute(self, context):
        bpy.ops.sequencer.movie_strip_add(
            filepath = self.filepath,
            frame_start = self.frame_start)
        bpy.ops.sequencer.meta_make()
        print(self.filepath)
        # print(self.files)
        return {'FINISHED'}

    def invoke(self, context, event):
        self.filter_movie = True
        self.frame_start = context.scene.frame_start
        self.display_type = 'FILE_IMGDISPLAY'

        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

# ======================================================================
# =========================== User Interface ===========================
# ======================================================================

class GRAPH_PT_ADH_AnimationToolsFCurvePanel(bpy.types.Panel):
    bl_label = 'ADH Animation Tools'
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'

    @classmethod
    def poll(self, context):
        return context.active_object != None\
            and context.active_object.animation_data != None

    def draw(self, context):
        layout = self.layout

        row = layout.row(align=True)
        row.operator('graph.adh_fcurve_add_cycle_modifier')
        row.operator('graph.adh_fcurve_remove_cycle_modifier', icon="CANCEL", text='')

        row = layout.row(align=True)
        row.operator('graph.adh_fcurve_bake_action')

class VIEW3D_PT_ADH_AnimationToolsView3DPanel(bpy.types.Panel):
    bl_label = 'ADH Animation Tools'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    @classmethod
    def poll(self, context):
        return True

    def draw(self, context):
        layout = self.layout

        row = layout.row(align=True)
        row.prop(context.scene.tool_settings, "use_keyframe_insert_auto", text='')
        row.prop_search(context.scene.keying_sets_all, "active",
                        context.scene, "keying_sets_all", text='')

        col = layout.column(align=True)
        col.operator('object.adh_snap_to_object')

class VIEW3D_PT_ADH_AnimationToolsVSEPanel(bpy.types.Panel):
    bl_label = 'ADH Animation Tools'
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'

    @classmethod
    def poll(self, context):
        return True

    def draw(self, context):
        layout = self.layout

        col = layout.column(align=True)
        col.operator('sequencer.adh_grouped_movie_strip_add')
        col.operator('sequencer.movie_strip_add')

def register():
    bpy.utils.register_module(__name__)
    
def unregister():
    bpy.utils.unregister_module(__name__)

if __name__ == "__main__":
    register()
