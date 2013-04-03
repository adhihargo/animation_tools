# Author: Adhi Hargo (cadmus.sw@gmail.com)
# License: GPL v2

import bpy

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

class ADH_FCurveAddCycleModifierToAllChannels(bpy.types.Operator):
    """Add cycle modifier to all available f-curve channels"""
    bl_idname = 'graph.adh_fcurve_add_cycle_modifier'
    bl_label = 'Add Cycle Modifier'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(self, context):
        return context.active_object != None\
            and context.active_object.animation_data != None

    def execute(self, context):
        for curve in context.active_object.animation_data.action.fcurves:
            cm = None
            for m in curve.modifiers:
                if m.type == 'CYCLES':
                    cm = m
                    break
            if not cm:
                cm = curve.modifiers.new(type = 'CYCLES')
            cm.mode_before = cm.mode_after = 'REPEAT_OFFSET'
        return {'FINISHED'}

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
