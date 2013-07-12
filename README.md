OHA Animation Tools
===================

Blender addon containing tools for animation and custom render setting management. User can make presets for final render and animation preview render.

There's also a one-click animation preview video creation, where some render settings are temporarily modified for preview purpose. The resulting video will be saved in a separate folder, by default `opengl_render/`, at the same level as the blendfile's folder (e.g. preview file for `animation/sc01c02.blend` will be placed at `opengl_render/sc01c02.mov`).

Due to some technical hurdle I can't solve yet, the modified render settings will not be automatically restored on render completion. The addon will save original render settings, and provide a button to restore it.

