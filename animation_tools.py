# Author: Adhi Hargo (cadmus.sw@gmail.com)
# License: GPL v2

import bpy
import getpass
import os
import string
import shelve
import threading
from mathutils import Matrix, Vector
from bpy.app.handlers import persistent
from bl_operators.presets import AddPresetBase, ExecutePreset
from bpy.props import BoolProperty, IntProperty, PointerProperty,\
    StringProperty, FloatVectorProperty, EnumProperty, CollectionProperty

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
# ============================= Properties =============================
# ======================================================================

# Kelas berikut ini dipakai menyimpan setting render asli, sekaligus
# mengatur nilai default sebagian besar setting render khusus
# preview. Sebagian lagi nilainya diambil secara dinamis dari konteks
# (path file dan nama pengguna). Penamaannya berkorelasi dengan nama
# yang tertera dalam tooltip setting terkait dalam GUI.
#
# Seluruh kode modifikasi setting render ada pada fungsi
# "temp_settings" dalam operator "render.oha_opengl" persis di bawah
# definisi kelas ini.
class OHA_RenderOpenGL_Settings(bpy.types.PropertyGroup):
    space_show_only_render              = BoolProperty(default=True)
    render_use_stamp                    = BoolProperty(default=True)
    render_use_stamp_camera             = BoolProperty(default=False)
    render_use_stamp_date               = BoolProperty(default=True)
    render_use_stamp_filename           = BoolProperty(default=False)
    render_use_stamp_frame              = BoolProperty(default=True)
    render_use_stamp_lens               = BoolProperty(default=False)
    render_use_stamp_marker             = BoolProperty(default=False)
    render_use_stamp_note               = BoolProperty(default=True)
    render_use_stamp_render_time        = BoolProperty(default=False)
    render_use_stamp_scene              = BoolProperty(default=False)
    render_use_stamp_sequencer_strip    = BoolProperty(default=False)
    render_use_stamp_time               = BoolProperty(default=False)
    render_use_simplify                 = BoolProperty(default=False)
    render_use_antialiasing             = BoolProperty(default=False)

    render_stamp_note_text              = StringProperty(\
        name='Stamp',
        description="Template for stamp note, %(user)s substituted to user name,"\
            +" %(path)s to blendfile's name",
        default='%(user)s | %(path)s')
    render_filepath                     = StringProperty(\
        name='Folder',
        description="Folder name to substitute for blendfile's folder.",
        default='opengl_render')
    image_file_format                   = StringProperty(default='H264')
    ffmpeg_format                       = StringProperty(default='QUICKTIME')
    ffmpeg_codec                        = StringProperty(default='H264')
    ffmpeg_audio_codec                  = StringProperty(default='MP3')

    render_stamp_font_size              = IntProperty(default=20)
    render_resolution_percentage        = IntProperty(default=100)
    render_resolution_x                 = IntProperty()
    render_resolution_y                 = IntProperty()
    ffmpeg_video_bitrate                = IntProperty(default=6000)

    render_stamp_background             = FloatVectorProperty(subtype='COLOR', size=4,
                                                              default=(0,0,0,.5))

class OHA_RenderOpenGL_Props(bpy.types.PropertyGroup):
    restored = BoolProperty(default=True)

    temp = PointerProperty(type = OHA_RenderOpenGL_Settings)
    load = PointerProperty(type = OHA_RenderOpenGL_Settings)

class OHA_QuickLink_BlendFile(bpy.types.PropertyGroup):
    name = StringProperty(
        options = {'HIDDEN', 'SKIP_SAVE'})
    file_path = StringProperty(
        subtype="FILE_PATH",
        options = {'HIDDEN', 'SKIP_SAVE'})

def update_oha_quicklink_root_folder(self, context):
    bpy.ops.scene.oha_quicklink_populate('INVOKE_DEFAULT')

def update_oha_quicklink_list_filter(self, context):
    props = context.scene.oha.quicklink_props

    props.groups_collection.clear()
    bpy.ops.scene.oha_quicklink_populate()

class OHA_QuickLink_Props(bpy.types.PropertyGroup):
    root_folder = StringProperty(
        name="Root Folder",
        description="Only .blend files two levels below this folder will be listed.",
        subtype="DIR_PATH",
        update=update_oha_quicklink_root_folder)
    list_filter = StringProperty(
        name="List Filter",
        description="When not empty, filters the group list.",
        update=update_oha_quicklink_list_filter
        )
    groups = []
    groups_collection = CollectionProperty(
        type=OHA_QuickLink_BlendFile)
    groups_index = IntProperty(default=0)

# Outermost property class
class OHA_Props(bpy.types.PropertyGroup):
    opengl_props = PointerProperty(
        type = OHA_RenderOpenGL_Props,
        options = {'HIDDEN', 'SKIP_SAVE'})
    quicklink_props = PointerProperty(
        type = OHA_QuickLink_Props,
        options = {'HIDDEN', 'SKIP_SAVE'})

QUICKLINK_CACHE = os.path.join(bpy.utils.script_paths(subdir='addons')[-1],
                               "oha_quicklink_cache")

# ======================================================================
# ============================== Operators =============================
# ======================================================================

class RENDER_OT_oha_render_opengl_animation(bpy.types.Operator):
    """OpenGL render active viewport."""
    bl_idname = 'render.oha_opengl'
    bl_label = 'OHA OpenGL Render Animation'
    bl_options = {'REGISTER'}

    _timer = None

    # Fungsi modifikasi setting render.
    def temp_settings(self, context):
        space = context.space_data
        scene = context.scene
        render = scene.render
        image = render.image_settings
        ffmpeg = render.ffmpeg
        load = scene.oha.opengl_props.load

        # Setting render dan FFMPEG menggunakan nilai default yang
        # ditentukan dalam kelas OHA_RenderOpenGL_Props, kecuali yang
        # diatur manual dalam kode setelah ini.
        for key in render_static_keys:
            setattr(render, key, getattr(load, 'render_'+key))
        for key in ffmpeg_settings_keys:
            setattr(ffmpeg, key, getattr(load, 'ffmpeg_'+key))

        # Nama folder output didapat dengan mengganti folder file
        # .blend terbuka dengan apapun yang ditentukan pengguna. Nama
        # file output didapat dengan menghapus ekstensi file .blend
        # terbuka.
        blendpath = context.blend_data.filepath
        safechars = '_-.()' + string.digits + string.ascii_letters
        base_folder = ''.join(c for c in load.render_filepath if c in safechars)
        if blendpath:
            blenddir, blendfile = os.path.split(blendpath)
            blenddir0, blenddir1 = os.path.split(blenddir)
            if blenddir1:
                format_ext_dict = { "MPEG1" : '.mpg',
                                    "MPEG2" : '.mp2',
                                    "MPEG4" : '.mp4',
                                    "AVI" : '.avi',
                                    "QUICKTIME" : '.mov',
                                    "DV" : '.dv',
                                    "H264" : '.mp4',
                                    "XVID" : '.avi',
                                    "OGG" : '.ogg',
                                    "MKV" : '.mkv',
                                    "FLASH" : '.flv',
                                    "WAV" : '.wav',
                                    "MP3" : '.mp3'}
                renderfile = os.path.splitext(blendfile)[0] + format_ext_dict.get(ffmpeg.format)
                render.filepath = os.path.join(blenddir0, base_folder,
                                               renderfile)
        render.stamp_note_text = load.render_stamp_note_text\
            % dict(user=getpass.getuser(),
                   path=bpy.path.basename(blendpath) if blendpath\
                       else "*unsaved*")

        # Only Render hanya berlaku jika area jendela di mana operator
        # ini dijalankan adalah 3D View.
        if space.type == 'VIEW_3D':
            space.show_only_render = load.space_show_only_render
        # Tentukan format video, agar setting FFMPEG terpakai.
        image.file_format = load.image_file_format
        # Codec H.264 hanya dapat memproses video dengan resolusi
        # kelipatan dua.
        for key in ['resolution_x', 'resolution_y']:
            res = getattr(render, key)
            if res % 2 != 0:
                setattr(render, key, res + 1)

    def _check_render_thread(self, context):
        bpy.ops.render.oha_opengl_settings(save=False)

        return {'FINISHED'}

    def cancel(self, context):
        context.window_manager.event_timer_remove(self._timer)
        
        return {'CANCELLED'}

    def modal(self, context, event):
        if event.type == 'TIMER':
            return self.check_render_thread(context)

        return {'PASS_THROUGH'}

    def execute(self, context):
        wm = context.window_manager

        bpy.ops.render.oha_opengl_settings(save=True)
        self.temp_settings(context)

        bpy.ops.render.opengl('INVOKE_DEFAULT', animation=True, view_context=True)

        return {'FINISHED'}

    def invoke(self, context, event):
        return self.execute(context)

class RENDER_OT_oha_render_opengl_animation_settings(bpy.types.Operator):
    """Return to previous render settings."""
    bl_idname = 'render.oha_opengl_settings'
    bl_label = 'Restore Render Settings'
    bl_options = {'REGISTER'}

    save = BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def save_settings(self, context):
        scene = context.scene
        space = context.space_data
        props = context.scene.oha.opengl_props
        temp = props.temp

        if not props.restored:
            return {'CANCELLED'}

        if space.type == 'VIEW_3D':
            for key in space_settings_keys:
                setattr(temp, 'space_'+key, getattr(space, key))
        for key in render_settings_keys:
            setattr(temp, 'render_'+key, getattr(scene.render, key))
        for key in image_settings_keys:
            setattr(temp, 'image_'+key, getattr(scene.render.image_settings, key))
        for key in ffmpeg_settings_keys:
            setattr(temp, 'ffmpeg_'+key, getattr(scene.render.ffmpeg, key))

        props.restored = False

        return {'FINISHED'}

    def restore_settings(self, context):
        scene = context.scene
        space = context.space_data
        props = context.scene.oha.opengl_props
        temp = props.temp

        if props.restored:
            return {'CANCELLED'}

        if space.type == 'VIEW_3D':
            for key in space_settings_keys:
                setattr(space, key, getattr(temp, 'space_'+key))
        for key in render_settings_keys:
            setattr(scene.render, key, getattr(temp, 'render_'+key))
        for key in image_settings_keys:
            setattr(scene.render.image_settings, key, getattr(temp, 'image_'+key))
        for key in ffmpeg_settings_keys:
            setattr(scene.render.ffmpeg, key, getattr(temp, 'ffmpeg_'+key))

        props.restored = True

        return {'FINISHED'}

    def execute(self, context):
        if self.save:
            return self.save_settings(context)
        else:
            return self.restore_settings(context)

space_settings_keys = [
    'show_only_render']
render_settings_keys = frozenset([
    'use_stamp', 'use_stamp_camera', 'use_stamp_date', 'use_stamp_filename',
    'use_stamp_frame', 'use_stamp_lens', 'use_stamp_marker',
    'use_stamp_note', 'use_stamp_render_time', 'use_stamp_scene',
    'use_stamp_sequencer_strip', 'use_stamp_time', 'use_simplify',
    'stamp_note_text', 'stamp_background', 'stamp_font_size',
    'resolution_percentage', 'resolution_x', 'resolution_y',
    'use_antialiasing', 'filepath'])
render_static_keys = render_settings_keys\
    - set(['filepath', 'stamp_note_text',
           'resolution_x', 'resolution_y'])
image_settings_keys = [
    'file_format']
ffmpeg_settings_keys = [
    'format', 'codec', 'audio_codec', 'video_bitrate']

class RENDER_OT_oha_render_qc_preset_add(AddPresetBase, bpy.types.Operator):
    """Add a new preset containing all indicated settings."""
    bl_idname = 'render.oha_render_qc_preset_add'
    bl_label = 'Add Render QC Preset'
    bl_options = {'REGISTER', 'UNDO'}
    preset_menu = 'RENDER_MT_oha_qc_presets'
    preset_subdir = 'oha_render_qc'

    preset_defines = [
        "scene  = bpy.context.scene",
        "render = bpy.context.scene.render",
        "image  = bpy.context.scene.render.image_settings",
        "ffmpeg = bpy.context.scene.render.ffmpeg"
        ]

    preset_values = [
        "scene.use_preview_range",
        "render.engine",                        "render.antialiasing_samples",
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
        "image.file_format",                    "ffmpeg.format",
        "ffmpeg.codec",                         "ffmpeg.audio_codec",
        "ffmpeg.video_bitrate",                 "ffmpeg.audio_bitrate",
        "ffmpeg.audio_channels",                "ffmpeg.audio_volume",
        "ffmpeg.audio_mixrate",                 "ffmpeg.use_lossless_output",
        "ffmpeg.maxrate",                       "ffmpeg.minrate",
        "ffmpeg.muxrate",                       "ffmpeg.packetsize",
        "ffmpeg.gopsize",                       "ffmpeg.buffersize",
        ]

    @staticmethod
    def as_filename(name):  # could reuse for other presets
        for char in " !@#$%^&*(){}:\";'[]<>,.\\/?":
            name = name.replace(char, '_')
        return name.strip()

class RENDER_OT_oha_preview_preset_add(AddPresetBase, bpy.types.Operator):
    bl_idname = 'render.oha_preview_preset_add'
    bl_label = 'Add Preview Preset'
    bl_options = {'REGISTER', 'UNDO'}
    preset_menu = 'RENDER_MT_oha_preview_presets'
    preset_subdir = 'oha_preview'

    preset_defines = [
        "load = bpy.context.scene.oha.opengl_props.load"
        ]

    preset_values = [
        "load.render_use_stamp",
        "load.render_use_stamp_camera",
        "load.render_use_stamp_date",
        "load.render_use_stamp_filename",
        "load.render_use_stamp_frame",
        "load.render_use_stamp_lens",
        "load.render_use_stamp_marker",
        "load.render_use_stamp_note",
        "load.render_use_stamp_render_time",
        "load.render_use_stamp_scene",
        "load.render_use_stamp_sequencer_strip",
        "load.render_use_stamp_time",
        "load.render_use_simplify",
        "load.render_use_antialiasing",

        "load.render_stamp_note_text",
        "load.render_filepath",
        "load.image_file_format",
        "load.ffmpeg_format",
        "load.ffmpeg_codec",
        "load.ffmpeg_audio_codec",

        "load.render_stamp_font_size",
        "load.ffmpeg_video_bitrate",

        "load.render_stamp_background"
        ]

    def dump_settings(self, context):
        scene  = bpy.context.scene
        render = bpy.context.scene.render
        image  = bpy.context.scene.render.image_settings
        ffmpeg = bpy.context.scene.render.ffmpeg
        load = bpy.context.scene.oha.opengl_props.load

        # Resolution_Percentage must stay 100%
        render_keys = render_static_keys - set(['resolution_percentage'])
        for key in render_keys:
            setattr(load, 'render_'+key, getattr(scene.render, key))
        for key in image_settings_keys:
            setattr(load, 'image_'+key, getattr(scene.render.image_settings, key))
        for key in ffmpeg_settings_keys:
            setattr(load, 'ffmpeg_'+key, getattr(scene.render.ffmpeg, key))

    def invoke(self, context, event):
        if not self.remove_active:
            self.dump_settings(context)
        return super().invoke(context, event)

# Uses bpy.ops.nla.bake as starting point.
class GRAPH_OT_oha_fcurve_bake_action(bpy.types.Operator):
    """Bake object/pose loc/scale/rotation animation to a new action"""
    bl_idname = 'graph.oha_fcurve_bake_action'
    bl_label = 'Bake Action'
    bl_options = {'REGISTER', 'UNDO'}

    frame_start = IntProperty(
        name="Start Frame",
        description="Start frame for baking",
        min=0, max=300000,
        default=1,
        )

    frame_end = IntProperty(
        name="End Frame",
        description="End frame for baking",
        min=1, max=300000,
        default=250,
        )

    only_selected = BoolProperty(
        name="Only Selected",
        description="Only key selected bones",
        default=True,
        )

    only_visible = BoolProperty(
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

class GRAPH_OT_oha_fcurve_add_cycle_modifier(bpy.types.Operator):
    """Add cycle modifier to all available f-curve channels"""
    bl_idname = 'graph.oha_fcurve_add_cycle_modifier'
    bl_label = 'Add Cycle Modifier'
    bl_options = {'REGISTER', 'UNDO'}

    cycles_before = IntProperty(
        name = 'Cycles Before')

    cycles_after = IntProperty(
        name = 'Cycles After')

    mode_before = EnumProperty(
        name = 'Mode Before',
        items = [('NONE', 'No Cycles', ''),
                 ('REPEAT', 'Repeat Motion', ''),
                 ('REPEAT_OFFSET', 'Repeat with Offset', ''),
                 ('MIRROR', 'Repeat Mirrored', ''),
                 ],
        default = 'REPEAT_OFFSET')

    mode_after = EnumProperty(
        name = 'Mode After',
        items = [('NONE', 'No Cycles', ''),
                 ('REPEAT', 'Repeat Motion', ''),
                 ('REPEAT_OFFSET', 'Repeat with Offset', ''),
                 ('MIRROR', 'Repeat Mirrored', ''),
                 ],
        default = 'REPEAT_OFFSET')

    only_selected = BoolProperty(
        name="Only Selected",
        description="Only key selected bones",
        default=True,
        )

    only_visible = BoolProperty(
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

class GRAPH_OT_oha_fcurve_remove_cycle_modifier(bpy.types.Operator):
    """Removes cycle modifier from all available f-curve channels"""
    bl_idname = 'graph.oha_fcurve_remove_cycle_modifier'
    bl_label = 'Remove Cycle Modifier'
    bl_options = {'REGISTER', 'UNDO'}

    only_selected = BoolProperty(
        name="Only Selected",
        description="Only key selected bones",
        default=True,
        )

    only_visible = BoolProperty(
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

class VIEW3D_OT_oha_object_snap_to_prev_keyframe(bpy.types.Operator):
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

class VIEW3D_OT_oha_object_snap_to_object(bpy.types.Operator):
    """Snap active object/bone to selected object/bone."""
    bl_idname = 'object.oha_snap_to_object'
    bl_label = 'Snap to Object'
    bl_options = {'REGISTER', 'UNDO'}

    snap_rotation = BoolProperty(
        name="Rotation",
        description="Also adjusting rotation to reference object.",
        default=True,
        )

    snap_scale = BoolProperty(
        name="Scale",
        description="Also adjusting scale to reference object.",
        default=False,
        )

    snap_pbone_rotation_scale = BoolProperty(
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
            mat = active.matrix_world.inverted() * mat

            pbone = context.active_pose_bone
            for p in pbone.parent_recursive:
                mat = p.matrix_basis * mat
            mat[3][0] = mat[3][1] = mat[3][2] = 0
            pbone.matrix = mat

            # cursor_old = context.scene.cursor_location.copy()
            
            # context.scene.objects.active = target
            # bpy.ops.view3d.snap_cursor_to_active()

            # context.scene.objects.active = active
            # bpy.ops.view3d.snap_selected_to_cursor()

            # context.scene.cursor_location = cursor_old

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

class SEQUENCER_OT_oha_movie_strip_add(bpy.types.Operator):
    """Add one or more movie strips, each file's audio and video strips automatically grouped as one metastrip."""
    bl_idname = 'sequencer.oha_grouped_movie_strip_add'
    bl_label = 'Add Grouped Movie Strips'
    bl_options = {'REGISTER', 'UNDO'}

    files = CollectionProperty(
        name="File Path",
        type=bpy.types.OperatorFileListElement)
    directory = StringProperty(
        default='//', subtype='DIR_PATH',
        options={'HIDDEN'})

    frame_start = IntProperty(
        subtype='UNSIGNED',
        options={'HIDDEN'})
    filter_movie = BoolProperty(
        default=True,
        options={'HIDDEN'})
    filter_folder = BoolProperty(
        default=True,
        options={'HIDDEN'})

    channel = IntProperty(
        name='Channel',
        default=1,
        min=1,max=32)
    consecutive = BoolProperty(
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

class SCENE_OT_oha_quicklink_populate(bpy.types.Operator):
    """Populate list of .blend files within specified root folder."""
    bl_idname = 'scene.oha_quicklink_populate'
    bl_label = 'Populate Blendfile List'
    bl_options = {'REGISTER'}

    root_folder = ''
    folder_list = []
    folder_list_index = 0
    cache = {}

    use_cache = BoolProperty(default=True, options={'HIDDEN'})

    @classmethod
    def poll(self, context):
        props = context.scene.oha.quicklink_props
        return props.root_folder != '' and os.path.exists(props.root_folder)

    def _populate0(self, context):
        props = context.scene.oha.quicklink_props

        folder = self.folder_list[self.folder_list_index]
        self.folder_list_index += 1
        
        file_list = [os.path.join(folder, f)
                     for f in os.listdir(folder)
                     if os.path.isfile(os.path.join(folder, f))
                     and f.endswith('.blend')]

        for f in file_list:
            with bpy.data.libraries.load(f) as (data_from, data_to):
                for g in data_from.groups:
                    props.groups.append((g, f))

    def _populate1(self, context):
        props = context.scene.oha.quicklink_props

        if self.root_folder in self.cache.keys():
            props.groups = self.cache[self.root_folder]

        props.groups_collection.clear()
        for g, f in props.groups:
            if props.list_filter.lower() in str.lower(g+f):
                item = props.groups_collection.add()
                item.name = g
                item.file_path = f

    def modal(self, context, event):
        props = context.scene.oha.quicklink_props

        if self.folder_list_index < len(self.folder_list):
            self._populate0(context)
            return {'PASS_THROUGH'}

        self.cache[self.root_folder] = props.groups
        while len(self.cache) > 10:
            self.cache.pop(list(self.cache.keys())[0])
        self.cache.sync()
        self._populate1(context)

        return {'FINISHED'}

    def execute(self, context):
        props = context.scene.oha.quicklink_props
        self.root_folder = bpy.path.abspath(props.root_folder)
        self.cache = shelve.open(QUICKLINK_CACHE)
        self._populate1(context)

        return {'FINISHED'}

    def invoke(self, context, event):
        def listdir(directory):
            return [os.path.join(directory, f)
                    for f in os.listdir(directory)
                    if os.path.isdir(os.path.join(directory, f))
                    and not f.startswith('.')
                    and os.access(os.path.join(directory, f), os.R_OK)]
        wm = context.window_manager
        props = context.scene.oha.quicklink_props
        self.root_folder = bpy.path.abspath(props.root_folder)
        self.cache = shelve.open(QUICKLINK_CACHE)

        if self.use_cache and self.root_folder in self.cache.keys():
            self._populate1(context)
            return {'FINISHED'}

        if not os.access(self.root_folder, os.R_OK):
            return {'CANCELLED'}

        props.groups.clear()
        self.folder_list.clear()

        folder0_list = listdir(self.root_folder)

        for folder in folder0_list:
            self.folder_list.append(folder)
            self.folder_list.extend(listdir(folder))
        self.folder_list.sort()
        
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
class SCENE_OT_oha_quicklink_makeproxy(bpy.types.Operator):
    """Link selected group into the scene, and create proxy."""
    bl_idname = 'scene.oha_quicklink_makeproxy'
    bl_label = 'Make Proxy'
    bl_options = {'REGISTER', 'UNDO'}

    group_name = StringProperty(default='', options={'HIDDEN', 'SKIP_SAVE'})
    file_path = StringProperty(default='', options={'HIDDEN', 'SKIP_SAVE'})
    make_proxy = BoolProperty(default=True, options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(self, context):
        props = context.scene.oha.quicklink_props
        return len(props.groups_collection) > 0

    def execute(self, context):
        props = context.scene.oha.quicklink_props
        file_item = props.groups_collection[props.groups_index]

        group_name = file_item.name if self.group_name == ''\
            else self.group_name
        group_dirname, group_basename = os.path.split(
            file_item.file_path if self.file_path == ''\
                else self.file_path)

        gd = dict(fullpath = file_item.file_path, basepath = group_basename,
                  group = group_name, sep = os.sep)

        group_fpath = "%(fullpath)s%(sep)sGroup%(sep)s%(group)s" % gd
        group_dpath = "%(fullpath)s%(sep)sGroup%(sep)s" % gd

        bpy.ops.wm.link_append(
            filepath=group_fpath,
            filename=group_name,
            directory=group_dpath,
            filemode=1,
            link=True,
            autoselect=False,
            active_layer=True,
            instance_groups=True,
            relative_path=True)
        rig_list = [o.name for o in bpy.data.groups[group_name].objects
                    if o.type == 'ARMATURE']
        rig_name = rig_list[0] if rig_list else None

        if rig_name:
            bpy.ops.object.proxy_make(object = rig_name)
            context.active_object.name = group_name + "_rig"
            bpy.ops.object.posemode_toggle()

        return {'FINISHED'}

class SCENE_OT_oha_reinstance_missing_groups(bpy.types.Operator):
    """Attempt to reinstance missing groups caused by broken file links."""
    bl_idname = 'scene.oha_reinstance_missing_groups'
    bl_label = 'Reinstance Missing Groups'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        props = scene.oha.quicklink_props

        empty_objects = [o for o in scene.objects
                         if o.type == 'EMPTY' and o.dupli_group == None]

        if not empty_objects:
            return {'CANCELLED'}

        for empty in empty_objects:
            matching_groups = [(g, f) for (g, f) in props.groups
                               if empty.name.startswith(g)]
            if not matching_groups:
                continue

            name_empty = empty.name
            matrix_empty = empty.matrix_world

            g, f = matching_groups[0]
            bpy.ops.scene.oha_quicklink_makeproxy(group_name=g, file_path=f,
                                                  make_proxy=False)

            new_empty = context.active_object
            new_empty.matrix_world = matrix_empty
            new_empty.name = name_empty
            new_empty.name = name_empty # Bump original object's name

            scene.objects.unlink(empty)

        return {'FINISHED'}
            

# ======================================================================
# =========================== User Interface ===========================
# ======================================================================

class SCENE_UL_oha_quicklink_groups(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_propname, index):
        props = context.scene.oha.quicklink_props
        layout.label(text="%s (%s)" % (item.name, os.path.basename(item.file_path)))

class RENDER_MT_oha_qc_presets(bpy.types.Menu):
    '''Presets for final render settings.'''
    bl_label = "Render Presets"
    bl_idname = "RENDER_MT_oha_qc_presets"
    preset_subdir = "oha_render_qc"
    preset_operator = "script.execute_preset"
    
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

    draw = bpy.types.Menu.draw_preset
    # def draw(self, context):
    #     bpy.types.Menu.draw_preset(self, context)

class RENDER_MT_oha_preview_presets(bpy.types.Menu):
    '''Presets for preview render settings.'''
    bl_label = "Preview Presets"
    bl_idname = "RENDER_MT_oha_preview_presets"
    preset_subdir = "oha_preview"
    preset_operator = "script.execute_preset"

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

    draw = bpy.types.Menu.draw_preset
        
class RENDER_PT_oha_render_panel(bpy.types.Panel):
    bl_label = 'OHA Render Settings'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'render'

    def draw(self, context):
        layout = self.layout

        col = layout.column_flow(align=True)
        col.label('Presets:')
        row = col.row(align=True)
        row.menu("RENDER_MT_oha_qc_presets",
                 text=bpy.types.RENDER_MT_oha_qc_presets.bl_label)
        row.operator("render.oha_render_qc_preset_add", text="", icon='ZOOMIN')
        row.operator("render.oha_render_qc_preset_add", text="", icon='ZOOMOUT').remove_active = True

        row = col.row(align=True)
        row.menu("RENDER_MT_oha_preview_presets",
                 text=bpy.types.RENDER_MT_oha_preview_presets.bl_label)
        row.operator("render.oha_preview_preset_add", text="", icon='ZOOMIN')
        row.operator("render.oha_preview_preset_add", text="", icon='ZOOMOUT').remove_active = True

        box = layout.box()
        col = box.column_flow(align=True)
        col.label('Preview Settings:')
        col.prop(context.scene.oha.opengl_props.load, 'render_filepath')
        col.prop(context.scene.oha.opengl_props.load, 'render_stamp_note_text')

class GRAPH_PT_oha_animation_tools(bpy.types.Panel):
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

class VIEW3D_PT_oha_animation_tools(bpy.types.Panel):
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

class SEQUENCER_PT_oha_animation_tools(bpy.types.Panel):
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

class SCENE_PT_oha_quicklink(bpy.types.Panel):
    bl_label = 'OHA Quick Link'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'scene'

    def draw(self, context):
        scene = context.scene
        props = scene.oha.quicklink_props
        layout = self.layout

        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(props, "root_folder", text="")
        prop = row.operator("scene.oha_quicklink_populate",
                            icon='FILE_REFRESH', text='')
        prop.use_cache = False
        col.prop(props, "list_filter", text="")

        col = layout.row()
        row = col.column()
        row.template_list("SCENE_UL_oha_quicklink_groups", "", props,
                          "groups_collection",
                          props, "groups_index", rows=10)

        row = col.column(align=True)
        row.operator("scene.oha_quicklink_makeproxy", icon='ZOOMIN', text='')
        row.operator("scene.oha_reinstance_missing_groups",
                     icon='MODIFIER', text='')


# ======================================================================
# ========================= Auxiliary Functions ========================
# ======================================================================

def view3d_header_renderpreview(self, context):
    layout = self.layout
    props = context.scene.oha.opengl_props

    row = layout.row(align=True)
    row.operator('render.oha_opengl', icon='RENDER_ANIMATION', text='Preview')
    row.operator('render.oha_opengl_settings', icon='DISK_DRIVE'
                 if props.restored else 'LOAD_FACTORY', text='')

def register():
    bpy.utils.register_module(__name__)
    bpy.types.VIEW3D_HT_header.append(view3d_header_renderpreview)
    bpy.types.Scene.oha = PointerProperty(
        type = OHA_Props,
        options = {'HIDDEN', 'SKIP_SAVE'})

def unregister():
    bpy.utils.unregister_module(__name__)
    bpy.types.VIEW3D_HT_header.remove(view3d_header_renderpreview)
    del bpy.types.Scene.oha_props

if __name__ == "__main__":
    register()
