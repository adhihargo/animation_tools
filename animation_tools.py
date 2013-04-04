# Author: Adhi Hargo (cadmus.sw@gmail.com)
# License: GPL v2

import bpy
from mathutils import Vector

bl_info = {
    "name": "ADH Animation Tools",
    "author": "Adhi Hargo",
    "version": (1, 0, 0),
    "blender": (2, 65, 0),
    "location": "F-Curve Editor > Tools",
    "description": "Various animation tools.",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Animation"}

def bake_action(obj, frame_start, frame_end, only_selected, action=None):
    action = obj.animation_data.action
    for fcurve in action.fcurves:
        print(fcurve.data_path)
        if len(fcurve.modifiers) == 1 and fcurve.modifiers[0].type == 'CYCLES':
            cm = fcurve.modifiers[0]

            key_min = min(fcurve.keyframe_points, key=lambda x: x.co.x)
            key_max = max(fcurve.keyframe_points, key=lambda x: x.co.x)
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
                    key_new.handle_left = key.handle_left + key_offset
                    key_new.handle_right = key.handle_right + key_offset

                    if check_cycles_before(count):
                        break
                    if (key.co.x+key_offset.x) <= frame_start:
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
                    key_new.handle_left = key.handle_left + key_offset
                    key_new.handle_right = key.handle_right + key_offset

                    if check_cycles_after(count):
                        break
                    if (key.co.x+key_offset.x) >= frame_end:
                        break

            fcurve.modifiers.remove(cm)

    return action

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
        description="Only key selected object/bones",
        default=False,
        )

    @classmethod
    def poll(self, context):
        return context.active_object != None\
            and context.active_object.animation_data != None

    def execute(self, context):
        action = bake_action(context.active_object,
                             self.frame_start,
                             self.frame_end,
                             only_selected=False)

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

    @classmethod
    def poll(self, context):
        return context.active_object != None\
            and context.active_object.animation_data != None

    def draw(self, context):
        layout = self.layout
        row = layout.row()

        col = row.column(align=True)
        col.prop(self, 'mode_before', text='')
        col.prop(self, 'cycles_before')

        col = row.column(align=True)
        col.prop(self, 'mode_after', text='')
        col.prop(self, 'cycles_after')

    def execute(self, context):
        for curve in context.active_object.animation_data.action.fcurves:
            cm = None
            for m in curve.modifiers:
                if m.type == 'CYCLES':
                    cm = m
                    break
            if not cm:
                cm = curve.modifiers.new(type = 'CYCLES')
            cm.mode_before = self.mode_before
            cm.mode_after = self.mode_after
            cm.cycles_before = self.cycles_before
            cm.cycles_after = self.cycles_after

        context.area.tag_redraw()
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

class ADH_FCurveRemoveCycleModifierToAllChannels(bpy.types.Operator):
    """Removes cycle modifier from all available f-curve channels"""
    bl_idname = 'graph.adh_fcurve_remove_cycle_modifier'
    bl_label = 'Remove Cycle Modifier'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(self, context):
        return context.active_object != None\
            and context.active_object.animation_data != None

    def execute(self, context):
        for curve in context.active_object.animation_data.action.fcurves:
            for m in curve.modifiers:
                if m.type == 'CYCLES':
                    curve.modifiers.remove(m)

        context.area.tag_redraw()
        return {'FINISHED'}

class ADH_AnimationToolsFCurvePanel(bpy.types.Panel):
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

class ADH_AnimationToolsView3DPanel(bpy.types.Panel):
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

def register():
    bpy.utils.register_module(__name__)
    
def unregister():
    bpy.utils.unregister_module(__name__)

if __name__ == "__main__":
    register()
