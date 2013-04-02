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
        return context.mode == 'POSE' and context.active_object != None

    def execute(self, context):
        for curve in context.active_object.animation_data.action.fcurves:
            is_cycles_exist = [m.type == 'CYCLES' for m in curve.modifiers]
            if not True in is_cycles_exist:
                curve.modifiers.new(type = 'CYCLES')
        return {'FINISHED'}

class ADH_RiggingToolsFCurvePanel(bpy.types.Panel):
    bl_label = 'ADH Animation Tools'
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'

    @classmethod
    def poll(self, context):
        return True

    def draw(self, context):
        layout = self.layout
        layout.operator('graph.adh_fcurve_add_cycle_modifier', icon="FCURVE")

def register():
    bpy.utils.register_module(__name__)
    
def unregister():
    bpy.utils.unregister_module(__name__)

if __name__ == "__main__":
    register()
    