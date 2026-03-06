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
Align2Custom Addon Preferences
"""


import bpy
import rna_keymap_ui

from . import ui
from . import align2custom
from .align2custom import A2C_PIE_MODE_ITEMS


class A2C_Preferences(bpy.types.AddonPreferences):
    """
    Addon panel of the 'Preferences...' interface
    """

    bl_idname = __package__

    pref_smooth: bpy.props.BoolProperty(
        name="Smooth rotation",
        description="Performs smooth rotation between the current view and the target view",
        default=True,
    )

    pref_minimize_roll: bpy.props.BoolProperty(
        name="Minimize viewport roll",
        description="Tries to maintain the current viewport orientation (up/down/left/right) "
                    "by minimizing roll when aligning to specific viewpoints",
        default=False,
    )

    pref_set_orientation_to_view: bpy.props.BoolProperty(
        name="Set Transformation orientation to 'View' after entering Aligned View",
        description="Automatically sets the transform orientation to 'View' after aligning the viewport",
        default=False,
    )

    pref_set_orientation_to_view_for_custom: bpy.props.BoolProperty(
        name="Set Transformation orientation to 'View' for 'Align to Custom' too",
        description="Also apply 'Set orientation to View' when using Align to Custom. "
                    "Warning: This will make subsequent Align to Custom operations not work "
                    "until you reselect a custom orientation",
        default=False,
    )

    pref_use_view_orientation_in_aligned_view: bpy.props.BoolProperty(
        name="Set align to 'View' for new objects added in Aligned View",
        description="While in aligned view: set transform orientation to View and set 'New Objects > Align to' to View "
                    "(so added primitives use align='VIEW'). Your previous settings are restored when you leave aligned view",
        default=False,
    )

    pref_default_pie_mode: bpy.props.EnumProperty(
        name="Default mode for Relative Alignment Pie Menu",
        description="Which alignment mode is pre-selected when opening the pie menu",
        items=A2C_PIE_MODE_ITEMS,
        default='SELECTION',
    )

    pref_enable_relative_position_after_align: bpy.props.BoolProperty(
        name="Use Relative Alignment Pie Menu once in Aligned View",
        description="When the view is already aligned, the pie menu shows shows new pivot options"
                    "(rotate view 90° up/down/left/right/roll angles) instead of the original pie menu.",
        default=False,
    )

    def draw(self, context):
        """ Display preference options in panel """
        layout = self.layout

        # Behaviour section
        box = layout.box()
        box.label(text="General", icon='SETTINGS')
        box.prop(self, "pref_smooth")
        box.prop(self, "pref_minimize_roll")
        box.prop(self, "pref_set_orientation_to_view")
        row = box.row()
        row.separator(factor=2.0)
        sub = row.row()
        sub.enabled = self.pref_set_orientation_to_view
        sub.prop(self, "pref_set_orientation_to_view_for_custom")
        if self.pref_set_orientation_to_view and self.pref_set_orientation_to_view_for_custom:
            warn_row = box.row()
            warn_row.separator(factor=2.0)
            warn_box = warn_row.box()
            col = warn_box.column(align=True)
            col.alert = True
            col.label(text="Warning: This will select the 'View' orientation,", icon='ERROR')
            col.label(text="making Align to Custom not work until you")
            col.label(text="reselect a Custom Orientation.")

        box.prop(self, "pref_use_view_orientation_in_aligned_view")

        box.prop(self, "pref_enable_relative_position_after_align")
        row = box.row()
        row.separator(factor=2.0)
        sub = row.row()
        sub.enabled = self.pref_enable_relative_position_after_align
        sub.prop(self, "pref_default_pie_mode")

        # Keymap section
        box = layout.box()
        box.label(text="Keymap", icon='KEYINGSET')
        self._draw_keymap(context, box)

    def _draw_keymap(self, context, layout):
        wm = context.window_manager
        kc = wm.keyconfigs.user

        km = kc.keymaps.get(ui.KEYMAP_INFO['km_name'])
        if not km:
            return

        for kmi in km.keymap_items:
            if (kmi.idname == ui.KEYMAP_INFO['operator_idname']
                    and kmi.properties.get('name') == ui.KEYMAP_INFO['menu_name']):
                rna_keymap_ui.draw_kmi([], kc, km, kmi, layout, 0)
                break

        # Draw addon keymaps (pivot-by-drag, leave aligned view) from addon keyconfig
        kc_addon = wm.keyconfigs.addon
        if kc_addon:
            for km in kc_addon.keymaps:
                for kmi in km.keymap_items:
                    if kmi.idname in align2custom.A2C_KEYMAP_PREF_OPERATORS:
                        rna_keymap_ui.draw_kmi([], kc_addon, km, kmi, layout, 0)


# ## Registration ##############################################################

def register():
    bpy.utils.register_class(A2C_Preferences)


def unregister():
    bpy.utils.unregister_class(A2C_Preferences)
