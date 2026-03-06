# -*- coding: utf-8 -*-

# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation, either version 3
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.
#  If not, see <https://www.gnu.org/licenses/>.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>


"""
Align2Custom UI – pie menu, regular menus and menu registration
"""


import math
import bpy

from . import align2custom
from .align2custom import A2C_VIEWPOINT_ITEMS, A2C_PIE_MODE_ITEMS


# ## Global data ###############################################################

_pie_keymaps = []

# Keymap info exposed for preferences to draw the keymap editor
KEYMAP_INFO = {
    'km_name': '3D View',
    'space_type': 'VIEW_3D',
    'operator_idname': 'wm.call_menu_pie',
    'key': 'Q',
    'value': 'PRESS',
    'ctrl': True,
    'alt': True,
    'menu_name': 'VIEW3D_MT_a2c_pie',
}


# ## Pie operator ##############################################################

class VIEW3D_OT_a2c_pie_viewpoint(bpy.types.Operator):
    """Align view using the mode selected in the pie menu"""
    bl_idname = "view3d.a2c_pie_viewpoint"
    bl_label = "Align View (Pie)"
    bl_options = {'REGISTER'}

    prop_viewpoint: bpy.props.EnumProperty(
        items=A2C_VIEWPOINT_ITEMS,
        name="Point of view",
        default="TOP",
    )

    def execute(self, context):
        mode = context.window_manager.a2c_pie_mode
        if mode == 'EDGE':
            return bpy.ops.view3d.a2c_align_to_edge(prop_viewpoint=self.prop_viewpoint)
        bpy.ops.view3d.a2c(prop_align_mode=mode, prop_viewpoint=self.prop_viewpoint)
        return {'FINISHED'}


# ## Pie menu ##################################################################

class VIEW3D_MT_a2c_pie(bpy.types.Menu):
    bl_idname = "VIEW3D_MT_a2c_pie"
    bl_label = "Align 2 Custom"

    def draw(self, context):
        layout = self.layout
        pie = layout.menu_pie()

        wm = context.window_manager
        prefs = context.preferences.addons[__package__].preferences
        is_aligned = align2custom.is_viewport_aligned(context)
        use_relative = prefs.pref_enable_relative_position_after_align and is_aligned

        # Blender pie slot fill order:
        # 1-West  2-East  3-South  4-North  5-NW  6-NE  7-SW  8-SE

        if use_relative:
            # Relative layout: pivot 90°, roll, leave
            # 1 – West: pivot left
            op = pie.operator("view3d.a2c_pivot_view", icon='TRIA_LEFT', text="")
            op.direction = 'LEFT'
            # 2 – East: pivot right
            op = pie.operator("view3d.a2c_pivot_view", icon='TRIA_RIGHT', text="")
            op.direction = 'RIGHT'
            # 3 – South: pivot down
            op = pie.operator("view3d.a2c_pivot_view", icon='TRIA_DOWN', text="")
            op.direction = 'BOTTOM'
            # 4 – North: pivot up
            op = pie.operator("view3d.a2c_pivot_view", icon='TRIA_UP', text="")
            op.direction = 'TOP'
            # 5
            op = pie.operator("view3d.a2c_roll_view", icon='LOOP_BACK', text="Roll -90°")
            op.angle = math.radians(-90)
            # 6
            op = pie.operator("view3d.a2c_roll_view", icon='LOOP_FORWARDS', text="Roll +90°")
            op.angle = math.radians(90)
            # 7
            pie.operator("view3d.a2c_leave_aligned_view", icon='CANCEL', text="Leave")
            # 8
            op = pie.operator("view3d.a2c_roll_view", icon='CON_FOLLOWPATH', text="Roll +180°")
            op.angle = math.radians(180)

        else:
            # Standard layout: alignment viewpoints
            # When mode is EDGE, viewpoint slots are enabled only if exactly one edge is selected
            edge_ok = align2custom.has_single_edge_selected(context)
            viewpoint_enabled = (wm.a2c_pie_mode != 'EDGE') or edge_ok

            # 1 – West: Y / Front
            col = pie.column()
            col.enabled = viewpoint_enabled
            col.operator("view3d.a2c_pie_viewpoint", text="Y").prop_viewpoint = 'FRONT'
            # 2 – East: -Y / Back
            col = pie.column()
            col.enabled = viewpoint_enabled
            col.operator("view3d.a2c_pie_viewpoint", text="-Y").prop_viewpoint = 'BACK'
            # 3 – South: Smart (Nearest)
            col = pie.column()
            col.enabled = viewpoint_enabled
            col.operator("view3d.a2c_pie_viewpoint", icon='ORIENTATION_VIEW', text="Smart").prop_viewpoint = 'NEAREST'
            # 4 – North: mode selector (Custom, Cursor, Selection, Edge)
            box = pie.box()
            row = box.row(align=True)
            row.scale_x = 1.2
            row.scale_y = 1.2
            row.prop(wm, "a2c_pie_mode", expand=True, icon_only=True)
            # 5 – NW: Z / Top
            col = pie.column()
            col.enabled = viewpoint_enabled
            col.operator("view3d.a2c_pie_viewpoint", text="Z").prop_viewpoint = 'TOP'
            # 6 – NE: -X / Left
            col = pie.column()
            col.enabled = viewpoint_enabled
            col.operator("view3d.a2c_pie_viewpoint", text="-X").prop_viewpoint = 'LEFT'
            # 7 – SW: X / Right, and Leave only when aligned
            if is_aligned:
                box_sw = pie.box()
                row_sw = box_sw.row(align=True)
                sub = row_sw.row()
                sub.enabled = viewpoint_enabled
                sub.operator("view3d.a2c_pie_viewpoint", text="X").prop_viewpoint = 'RIGHT'
                row_sw.operator("view3d.a2c_leave_aligned_view", icon='CANCEL', text="Leave")
            else:
                col = pie.column()
                col.enabled = viewpoint_enabled
                col.operator("view3d.a2c_pie_viewpoint", text="X").prop_viewpoint = 'RIGHT'
            # 8 – SE: -Z / Bottom
            col = pie.column()
            col.enabled = viewpoint_enabled
            col.operator("view3d.a2c_pie_viewpoint", text="-Z").prop_viewpoint = 'BOTTOM'


# ## Regular menus #############################################################

class VIEW3D_MT_a2c(bpy.types.Menu):
    """
    Submenu 'Align View ...' base class
    """

    bl_idname = "VIEW3D_MT_a2c"
    bl_label = "Align View base class"

    def draw(self, context):
        self.create_items(context)

    def create_items(self, context, align_mode='CUSTOM'):
        use_edge = (align_mode == 'EDGE')
        op_idname = "view3d.a2c_align_to_edge" if use_edge else "view3d.a2c"

        # (label, viewpoint, separator_before)
        entries = (
            ("Top",     'TOP',     False),
            ("Bottom",  'BOTTOM',  False),
            ("Front",   'FRONT',   True),
            ("Back",    'BACK',    False),
            ("Right",   'RIGHT',   True),
            ("Left",    'LEFT',    False),
            ("Nearest", 'NEAREST', True),
        )
        for label, viewpoint, sep in entries:
            if sep:
                self.layout.separator()
            op = self.layout.operator(op_idname, text=label)
            op.prop_viewpoint = viewpoint
            if not use_edge:
                op.prop_align_mode = align_mode


class VIEW3D_MT_align2custom(VIEW3D_MT_a2c):
    """
    Submenu 'Align View to Custom': align to the active custom transform orientation
    """

    bl_idname = "VIEW3D_MT_align2custom"
    bl_label = "Align View to Custom"

    def draw(self, context):
        self.create_items(context, 'CUSTOM')


class VIEW3D_MT_align2cursor(VIEW3D_MT_a2c):
    """
    Submenu 'Align View to Cursor': align to the 3D cursor orientation
    """

    bl_idname = "VIEW3D_MT_align2cursor"
    bl_label = "Align View to Cursor"

    def draw(self, context):
        self.create_items(context, 'CURSOR')


class VIEW3D_MT_align2selection(VIEW3D_MT_a2c):
    """
    Submenu 'Align View to Selection': create a temporary orientation from the
    selection, align the view to it, then delete the temporary orientation
    """

    bl_idname = "VIEW3D_MT_align2selection"
    bl_label = "Align View to Selection"

    def draw(self, context):
        self.create_items(context, 'SELECTION')


class VIEW3D_MT_align2edge(VIEW3D_MT_a2c):
    """
    Submenu 'Align View to Edge': align so the selected edge is horizontal
    (Edit Mode, one edge selected). Same viewpoint choices as other align modes.
    """

    bl_idname = "VIEW3D_MT_align2edge"
    bl_label = "Align View to Edge"

    def draw(self, context):
        self.create_items(context, 'EDGE')


def a2c_menu_func(self, context):
    """
    Append the submenus to View3D > View > Align View
    """
    self.layout.separator()
    self.layout.menu(VIEW3D_MT_align2custom.bl_idname)
    self.layout.menu(VIEW3D_MT_align2cursor.bl_idname)
    self.layout.menu(VIEW3D_MT_align2selection.bl_idname)
    self.layout.menu(VIEW3D_MT_align2edge.bl_idname)


# ## Registration ##############################################################

_classes = (
    VIEW3D_OT_a2c_pie_viewpoint,
    VIEW3D_MT_a2c_pie,
    VIEW3D_MT_a2c,
    VIEW3D_MT_align2custom,
    VIEW3D_MT_align2cursor,
    VIEW3D_MT_align2selection,
    VIEW3D_MT_align2edge,
)


def register():
    bpy.types.WindowManager.a2c_pie_mode = bpy.props.EnumProperty(
        items=A2C_PIE_MODE_ITEMS,
        name="Align Mode",
        default='SELECTION',
    )

    for cls in _classes:
        bpy.utils.register_class(cls)

    bpy.types.VIEW3D_MT_view_align.append(a2c_menu_func)

    # Apply default pie mode from preferences
    try:
        prefs = bpy.context.preferences.addons[__package__].preferences
        bpy.context.window_manager.a2c_pie_mode = prefs.pref_default_pie_mode
    except Exception:
        pass

    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(
            name=KEYMAP_INFO['km_name'],
            space_type=KEYMAP_INFO['space_type'],
        )
        kmi = km.keymap_items.new(
            KEYMAP_INFO['operator_idname'],
            type=KEYMAP_INFO['key'],
            value=KEYMAP_INFO['value'],
            ctrl=KEYMAP_INFO['ctrl'],
            alt=KEYMAP_INFO['alt'],
        )
        kmi.properties.name = KEYMAP_INFO['menu_name']
        _pie_keymaps.append((km, kmi))


def unregister():
    bpy.types.VIEW3D_MT_view_align.remove(a2c_menu_func)

    for km, kmi in _pie_keymaps:
        km.keymap_items.remove(kmi)
    _pie_keymaps.clear()

    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.WindowManager.a2c_pie_mode
