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

# Contributed to by fdaubine


"""
Align2Custom module implementation
"""


import math
import mathutils as mu
import threading as thd
import time
import bpy


# ## Global data ##############################################################
GL_ADDON_KEYMAPS = []       # Keymap collection
GL_TOKEN_LOCK = False       # Locking token while rotating 3D View
# Storage for original perspective mode and rotation state for each area
GL_VIEWPORT_STATE = {}      # Format: {area_ptr: {'original_perspective': str, 'aligned_rotation': quaternion, 'is_aligned': bool}}
GL_DRAW_HANDLER = None      # Draw handler for monitoring viewport changes


# ## Viewport monitoring system ###############################################
def get_area_pointer(area):
    """Get a unique pointer identifier for a 3D viewport area"""
    if area and area.type == 'VIEW_3D':
        return area.as_pointer()
    return None


def store_viewport_state(area, original_perspective, aligned_rotation):
    """Store the original viewport state before alignment"""
    area_ptr = get_area_pointer(area)
    if area_ptr:
        global GL_VIEWPORT_STATE
        GL_VIEWPORT_STATE[area_ptr] = {
            'original_perspective': original_perspective,
            'aligned_rotation': aligned_rotation,
            'is_aligned': True
        }


def check_and_restore_perspective():
    """Check if user has rotated away from aligned view and restore original perspective if so"""
    global GL_VIEWPORT_STATE, GL_TOKEN_LOCK
    
    # Don't check during smooth rotation animation - it interferes with the transition
    if GL_TOKEN_LOCK:
        return
    
    # Iterate through all windows and areas to check for rotation changes
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area_ptr = get_area_pointer(area)
                if area_ptr and area_ptr in GL_VIEWPORT_STATE:
                    state = GL_VIEWPORT_STATE[area_ptr]
                    if state['is_aligned']:
                        space = area.spaces[0]
                        current_rotation = space.region_3d.view_rotation
                        aligned_rotation = state['aligned_rotation']
                        
                        # Calculate rotation difference using quaternion dot product
                        # Dot product close to 1.0 means rotations are similar
                        dot_product = abs(current_rotation.dot(aligned_rotation))
                        
                        # Threshold for considering rotations as "different"
                        # 0.999 corresponds to about 2.5 degrees difference
                        rotation_threshold = 0.999
                        
                        # If the rotation has changed significantly, restore original perspective
                        if dot_product < rotation_threshold:
                            space.region_3d.view_perspective = state['original_perspective']
                            state['is_aligned'] = False  # Mark as no longer aligned


def viewport_draw_handler():
    """Draw handler to monitor viewport rotation changes"""
    try:
        check_and_restore_perspective()
    except Exception:
        # Silently handle any errors to avoid disrupting the viewport
        pass


def cleanup_viewport_state(area_ptr):
    """Clean up viewport state for areas that no longer exist"""
    global GL_VIEWPORT_STATE
    if area_ptr in GL_VIEWPORT_STATE:
        del GL_VIEWPORT_STATE[area_ptr]


# ## Math functions section ###################################################
def s_curve(x):
    """
    Function that returns the transformation of a linear value by a s-curve
    function.

    Parameter :
     - x [in] : float value [0.0, 1.0]

    Return value : float value
    """

    assert (0.0 <= x <= 1.0), ("Overflow error : argument 'x' should "
                               "be in the range [0, 1]")

    return (1.0 + math.sin((x - 0.5) * math.pi))/2.0


def find_best_roll_orientation(current_quat, target_base_matrix, viewpoint_matrix):
    """
    Find the best roll orientation by preserving the visual "up" direction after cursor alignment.
    
    Simple approach:
    1. Capture the current visual "up" direction in world space
    2. Do proper cursor alignment 
    3. Apply 90-degree rotation to restore the visual "up" direction as closely as possible
    
    Parameters:
     - current_quat: Current view rotation quaternion
     - target_base_matrix: Base matrix (cursor or custom orientation)
     - viewpoint_matrix: Viewpoint rotation matrix (TOP, FRONT, etc.)
    
    Returns: Final orientation matrix with cursor alignment and preserved visual orientation
    """
    
    # Step 1: Capture the current visual "up" direction in world space
    current_matrix = current_quat.to_matrix()
    
    # The current "up" direction is what appears to go upward in the viewport
    # This is the Y-axis (column) of the current view matrix
    # Note: matrix[1] gets the ROW, matrix.col[1] gets the COLUMN (Y-axis)
    visual_up_direction = current_matrix.col[1]  # Y-axis column (up direction in viewport)
    
    # Step 2: Do the standard cursor alignment
    aligned_matrix = target_base_matrix @ viewpoint_matrix
    
    # Step 3: Test 90-degree rotations to find the one that best preserves visual "up"
    best_rotation = 0
    best_score = -1
    
    for rotation_degrees in [0, 90, 180, 270]:
        # Apply the test rotation around the view direction (Z-axis)
        rotation_radians = math.radians(rotation_degrees)
        rotation_matrix = mu.Matrix.Rotation(rotation_radians, 3, 'Z')
        test_matrix = aligned_matrix @ rotation_matrix
        
        # Get the new "up" direction after this rotation
        new_up_direction = test_matrix.col[1]  # Y-axis column of the rotated matrix
        
        # Score based on how closely the new "up" matches the original visual "up"
        # Use dot product - closer to 1.0 means better alignment
        alignment_score = visual_up_direction.dot(new_up_direction)
        
        # We want the highest dot product (closest to 1.0)
        if alignment_score > best_score:
            best_score = alignment_score
            best_rotation = rotation_degrees
    
    # Step 4: Apply the best rotation
    final_rotation_matrix = mu.Matrix.Rotation(math.radians(best_rotation), 3, 'Z')
    final_matrix = aligned_matrix @ final_rotation_matrix
    
    return final_matrix


# ## Preferences section ######################################################
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
        description="Tries to maintain the current viewport orientation (up/down/left/right) by minimizing roll when aligning to specific viewpoints",
        default=False,
    )
    
    pref_set_orientation_to_view: bpy.props.BoolProperty(
        name="Set orientation to View after aligning",
        description="Automatically sets the transform orientation to 'View' after aligning the viewport",
        default=False,
    )
    
    pref_set_orientation_to_view_for_custom: bpy.props.BoolProperty(
        name="For Align to Custom too",
        description="Also apply 'Set orientation to View' when using Align to Custom. Warning: This will make subsequent Align to Custom operations not work until you reselect a custom orientation",
        default=False,
    )

    def draw(self, context):
        """ Display preference options in panel """
        layout = self.layout
        layout.prop(self, "pref_smooth")
        layout.prop(self, "pref_minimize_roll")
        layout.prop(self, "pref_set_orientation_to_view")
        
        # Sub-option for "Align to Custom" - nested and greyed out if parent is disabled
        row = layout.row()
        row.separator(factor=2.0)  # Indentation
        sub = row.row()
        sub.enabled = self.pref_set_orientation_to_view
        sub.prop(self, "pref_set_orientation_to_view_for_custom")
        
        # Show warning when this option is enabled
        if self.pref_set_orientation_to_view and self.pref_set_orientation_to_view_for_custom:
            warn_row = layout.row()
            warn_row.separator(factor=2.0)  # Match indentation
            box = warn_row.box()
            col = box.column(align=True)
            col.alert = True  # Makes the text red
            col.label(text="Warning: This will select the 'View' orientation,", icon='ERROR')
            col.label(text="making Align to Custom not work until you")
            col.label(text="reselect a Custom Orientation.")


# ## Operator section #########################################################
class VIEW3D_OT_a2c(bpy.types.Operator):
    """
    Align 3D View to 3D cursor or active custom transform orientation
    """

    bl_idname = "view3d.a2c"
    bl_label = "Align to 3D cursor or custom transform orientation"
    bl_options = {'REGISTER'}

    ALIGN_MODE_ITEMS = [
        ("CUSTOM", "Align to custom orientation", "", 1),
        ("CURSOR", "Align to cursor orientation", "", 2),
        ("SELECTION", "Align to selection orientation", "", 3),
    ]

    VIEWPOINT_ITEMS = [
        ("TOP", "Top view", "", 1),
        ("BOTTOM", "Bottom view", "", 2),
        ("FRONT", "Front view", "", 3),
        ("BACK", "Back view", "", 4),
        ("RIGHT", "Right view", "", 5),
        ("LEFT", "Left view", "", 6),
        ("NEAREST", "Nearest view", "", 7),
    ]

    prop_align_mode: bpy.props.EnumProperty(items=ALIGN_MODE_ITEMS,
                                            name="Align mode",
                                            default="CUSTOM")
    prop_viewpoint: bpy.props.EnumProperty(items=VIEWPOINT_ITEMS,
                                           name="Point of view",
                                           default="TOP")

    SMOOTH_ROT_STEP = 0.02
    SMOOTH_ROT_DURATION = 0.24

    @staticmethod
    def smooth_rotate(space, quat_begin, quat_end):
        """
        Rotate the 3D view smoothly between the quaternions 'quat_begin' and
        'quat_end'
        """

        global GL_TOKEN_LOCK

        if space:
            # Calculation of the rotation angle which is used to compute the
            # smooth rotation duration
            diff_quat = quat_end.rotation_difference(quat_begin)
            _, angle = diff_quat.to_axis_angle()
            duration = abs(VIEW3D_OT_a2c.SMOOTH_ROT_DURATION * angle / math.pi)

            start_time = time.time()
            current_time = start_time

            while current_time <= start_time + duration:
                if duration == 0.0:
                    factor = 1.0
                else:
                    factor = s_curve((current_time - start_time) / duration)
                orientation = quat_begin.slerp(quat_end, factor)
                space.region_3d.view_rotation = orientation

                time.sleep(VIEW3D_OT_a2c.SMOOTH_ROT_STEP)
                current_time = time.time()

            space.region_3d.view_rotation = quat_end
            # Ensure ORTHO view is set after rotation completes
            space.region_3d.view_perspective = 'ORTHO'

        GL_TOKEN_LOCK = False

    def execute(self, context):
        """
        Set the orientation of the 3D View in which the operator is called,
        as a combination of the 3D cursor matrix or the active custom transform
        orientation matrix, and the rotation matrix passed in argument.

        The rotation transition depends on the parameter selected in the addon
        preferences UI. The transition can be instantaneous or smooth.
        """

        global GL_TOKEN_LOCK

        # Get the addon preferences
        prefs = context.preferences.addons[__package__].preferences

        scene = context.window.scene
        space = context.space_data

        # Handle SELECTION mode: create temporary orientation from selection
        temp_orientation_created = False
        if self.prop_align_mode == 'SELECTION':
            try:
                # Create temporary custom orientation from selection
                bpy.ops.transform.create_orientation(
                    name="Temp",
                    use=True,
                    overwrite=True
                )
                temp_orientation_created = True
            except RuntimeError:
                # No valid selection to create orientation from
                self.report({'WARNING'}, "Cannot create orientation from current selection")
                return {'CANCELLED'}

        co = scene.transform_orientation_slots[0].custom_orientation
        can_proceed = (self.prop_align_mode == 'CURSOR') or \
                      (self.prop_align_mode == 'SELECTION' and temp_orientation_created) or \
                      (self.prop_align_mode == 'CUSTOM' and co)
        
        if (not GL_TOKEN_LOCK) and (space.type == 'VIEW_3D') and can_proceed:

            # Store original perspective mode before alignment
            original_perspective = space.region_3d.view_perspective

            # Determine the base matrix first (needed for NEAREST calculation)
            if self.prop_align_mode == 'CURSOR':
                base_matrix = scene.cursor.matrix.to_3x3()
            else:
                # Both CUSTOM and SELECTION modes use the custom orientation
                base_matrix = co.matrix.copy()

            # Define all viewpoint rotation matrices
            viewpoint_matrices = {
                "TOP": mu.Matrix.Identity(3),
                "BOTTOM": mu.Matrix.Rotation(math.radians(180.0), 3, 'X'),
                "FRONT": mu.Matrix.Rotation(math.radians(90.0), 3, 'X'),
                "BACK": mu.Matrix.Rotation(math.radians(90.0), 3, 'X') @ mu.Matrix.Rotation(math.radians(180.0), 3, 'Y'),
                "RIGHT": mu.Matrix.Rotation(math.radians(90.0), 3, 'X') @ mu.Matrix.Rotation(math.radians(90.0), 3, 'Y'),
                "LEFT": mu.Matrix.Rotation(math.radians(90.0), 3, 'X') @ mu.Matrix.Rotation(math.radians(-90.0), 3, 'Y')
            }

            # Compute the rotation matrix according to the desired viewpoint
            if self.prop_viewpoint == "NEAREST":
                # Find the nearest viewpoint based on VIEW DIRECTION only (ignoring roll)
                current_quat = space.region_3d.view_rotation
                
                # Get the current view direction (the direction the camera is looking)
                # In Blender, the view looks down the -Z axis of the view rotation
                current_view_matrix = current_quat.to_matrix()
                current_view_direction = -current_view_matrix.col[2]  # -Z axis is view direction
                
                max_dot = -float('inf')
                best_viewpoint = "TOP"
                
                for viewpoint_name, viewpoint_rot in viewpoint_matrices.items():
                    # Calculate the target orientation for this viewpoint
                    target_orientation = base_matrix @ viewpoint_rot
                    
                    # Get the view direction for this target (what direction the camera would look)
                    target_view_direction = -target_orientation.col[2]  # -Z axis is view direction
                    
                    # Compare directions using dot product (higher = more aligned)
                    # dot product of 1.0 means identical directions, -1.0 means opposite
                    dot = current_view_direction.dot(target_view_direction)
                    
                    if dot > max_dot:
                        max_dot = dot
                        best_viewpoint = viewpoint_name
                
                # Use the rotation matrix of the best viewpoint
                rot_matrix = viewpoint_matrices[best_viewpoint]
            elif self.prop_viewpoint in viewpoint_matrices:
                rot_matrix = viewpoint_matrices[self.prop_viewpoint]
            else:   # TOP (DEFAULT)
                rot_matrix = mu.Matrix.Identity(3)

            # Use minimize roll feature if enabled
            if prefs.pref_minimize_roll:
                current_quat = space.region_3d.view_rotation
                new_orientation = find_best_roll_orientation(current_quat, base_matrix, rot_matrix)
            else:
                new_orientation = base_matrix @ rot_matrix

            final_quat = new_orientation.to_quaternion()

            # Delete temporary orientation if we created one (SELECTION mode)
            if temp_orientation_created:
                try:
                    bpy.ops.transform.delete_orientation()
                except RuntimeError:
                    pass  # Orientation might already be deleted

            # Store viewport state before making changes
            store_viewport_state(context.area, original_perspective, final_quat)

            space.region_3d.view_perspective = 'ORTHO'

            if prefs.pref_smooth:
                initial_quat = space.region_3d.view_rotation
                rotation_job = thd.Thread(
                                    target=VIEW3D_OT_a2c.smooth_rotate,
                                    args=(space, initial_quat, final_quat))

                GL_TOKEN_LOCK = True
                rotation_job.start()
            else:
                space.region_3d.view_rotation = final_quat

            # Set transform orientation to View if preference is enabled
            # For CUSTOM mode, also check the "for custom too" sub-option
            should_set_view_orientation = prefs.pref_set_orientation_to_view and (
                self.prop_align_mode != 'CUSTOM' or prefs.pref_set_orientation_to_view_for_custom
            )
            if should_set_view_orientation:
                scene.transform_orientation_slots[0].type = 'VIEW'

        else:
            # If we couldn't proceed but created a temp orientation, clean it up
            if temp_orientation_created:
                try:
                    bpy.ops.transform.delete_orientation()
                except RuntimeError:
                    pass

        return {'FINISHED'}


# ## Menus section ############################################################
class VIEW3D_MT_a2c(bpy.types.Menu):
    """
    Submenu 'Align View ...' base class
    """

    bl_idname = "VIEW3D_MT_a2c"
    bl_label = "Align View base class"

    def draw(self, context):
        """ Display menu items """
        self.create_items(context)

    def create_items(self, context, align_mode='CUSTOM'):
        """ Create menu items """
        operator_prop = self.layout.operator(VIEW3D_OT_a2c.bl_idname,
                                             text="Top")
        operator_prop.prop_viewpoint = 'TOP'
        operator_prop.prop_align_mode = align_mode
        operator_prop = self.layout.operator(VIEW3D_OT_a2c.bl_idname,
                                             text="Bottom")
        operator_prop.prop_viewpoint = 'BOTTOM'
        operator_prop.prop_align_mode = align_mode

        self.layout.separator()

        operator_prop = self.layout.operator(VIEW3D_OT_a2c.bl_idname,
                                             text="Front")
        operator_prop.prop_viewpoint = 'FRONT'
        operator_prop.prop_align_mode = align_mode
        operator_prop = self.layout.operator(VIEW3D_OT_a2c.bl_idname,
                                             text="Back")
        operator_prop.prop_viewpoint = 'BACK'
        operator_prop.prop_align_mode = align_mode

        self.layout.separator()

        operator_prop = self.layout.operator(VIEW3D_OT_a2c.bl_idname,
                                             text="Right")
        operator_prop.prop_viewpoint = 'RIGHT'
        operator_prop.prop_align_mode = align_mode
        operator_prop = self.layout.operator(VIEW3D_OT_a2c.bl_idname,
                                             text="Left")
        operator_prop.prop_viewpoint = 'LEFT'
        operator_prop.prop_align_mode = align_mode
        
        # Add "Nearest" option for all alignment modes
        self.layout.separator()
        operator_prop = self.layout.operator(VIEW3D_OT_a2c.bl_idname,
                                             text="Nearest")
        operator_prop.prop_viewpoint = 'NEAREST'
        operator_prop.prop_align_mode = align_mode


class VIEW3D_MT_align2custom(VIEW3D_MT_a2c):
    """
    Submenu 'Align View to Custom' : offers to select one of the 6 possible
    orientations (Top, Bottom, Front, Back, Right, Left) according to the
    selected custom transform orientation axes
    """

    bl_idname = "VIEW3D_MT_align2custom"
    bl_label = "Align View to Custom"

    def draw(self, context):
        """ Display menu items """
        self.create_items(context, 'CUSTOM')


class VIEW3D_MT_align2cursor(VIEW3D_MT_a2c):
    """
    Submenu 'Align View to Cursor' : offers to select one of the 6 possible
    orientations (Top, Bottom, Front, Back, Right, Left) according to the
    3D cursor axes
    """

    bl_idname = "VIEW3D_MT_align2cursor"
    bl_label = "Align View to Cursor"

    def draw(self, context):
        """ Display menu items """
        self.create_items(context, 'CURSOR')


class VIEW3D_MT_align2selection(VIEW3D_MT_a2c):
    """
    Submenu 'Align View to Selection' : creates a temporary custom orientation
    from the current selection, aligns the view to it, then deletes the
    temporary orientation. Offers the 6 possible orientations (Top, Bottom,
    Front, Back, Right, Left).
    """

    bl_idname = "VIEW3D_MT_align2selection"
    bl_label = "Align View to Selection"

    def draw(self, context):
        """ Display menu items """
        self.create_items(context, 'SELECTION')


def a2c_menu_func(self, context):
    """
    Append the submenus 'Align View to Custom', 'Align View to Cursor', and
    'Align View to Selection' to the menu 'View3D > View > Align View'
    """

    self.layout.separator()
    self.layout.menu(VIEW3D_MT_align2custom.bl_idname)
    self.layout.menu(VIEW3D_MT_align2cursor.bl_idname)
    self.layout.menu(VIEW3D_MT_align2selection.bl_idname)


# ## Blender registration section #############################################
def register():
    """
    Module register function called by the main package register function
    """
    global GL_ADDON_KEYMAPS, GL_DRAW_HANDLER

    bpy.utils.register_class(A2C_Preferences)
    bpy.utils.register_class(VIEW3D_OT_a2c)
    bpy.utils.register_class(VIEW3D_MT_a2c)
    bpy.utils.register_class(VIEW3D_MT_align2custom)
    bpy.utils.register_class(VIEW3D_MT_align2cursor)
    bpy.utils.register_class(VIEW3D_MT_align2selection)

    bpy.types.VIEW3D_MT_view_align.append(a2c_menu_func)

    # Register the viewport draw handler
    GL_DRAW_HANDLER = bpy.types.SpaceView3D.draw_handler_add(
        viewport_draw_handler, (), 'WINDOW', 'POST_PIXEL'
    )

    if bpy.context.window_manager.keyconfigs.addon:
        km = bpy.context.window_manager.keyconfigs.addon.keymaps.new(
            name='3D View',
            space_type='VIEW_3D')

        def set_km_item(km, key, ctrl, viewpoint, align_mode):
            global GL_ADDON_KEYMAPS

            if km:
                kmi = km.keymap_items.new(VIEW3D_OT_a2c.bl_idname,
                                          key, 'PRESS',
                                          alt=True, ctrl=ctrl)
                kmi.properties.prop_viewpoint = viewpoint
                kmi.properties.prop_align_mode = align_mode
                GL_ADDON_KEYMAPS.append((km, kmi))

        # Shortcuts for align to custom orientation operators
        set_km_item(km, 'NUMPAD_7', False, 'TOP', 'CUSTOM')
        set_km_item(km, 'NUMPAD_7', True, 'BOTTOM', 'CUSTOM')
        set_km_item(km, 'NUMPAD_1', False, 'FRONT', 'CUSTOM')
        set_km_item(km, 'NUMPAD_1', True, 'BACK', 'CUSTOM')
        set_km_item(km, 'NUMPAD_3', False, 'RIGHT', 'CUSTOM')
        set_km_item(km, 'NUMPAD_3', True, 'LEFT', 'CUSTOM')

        # Shortcuts for align to 3D cursor operators
        set_km_item(km, 'NUMPAD_8', False, 'TOP', 'CURSOR')
        set_km_item(km, 'NUMPAD_8', True, 'BOTTOM', 'CURSOR')
        set_km_item(km, 'NUMPAD_5', False, 'FRONT', 'CURSOR')
        set_km_item(km, 'NUMPAD_5', True, 'BACK', 'CURSOR')
        set_km_item(km, 'NUMPAD_6', False, 'RIGHT', 'CURSOR')
        set_km_item(km, 'NUMPAD_6', True, 'LEFT', 'CURSOR')


def unregister():
    """
    Module unregister function called by the main package register function
    """
    global GL_ADDON_KEYMAPS, GL_VIEWPORT_STATE, GL_DRAW_HANDLER

    # Clean up global state
    GL_VIEWPORT_STATE.clear()

    # Remove the viewport draw handler
    if GL_DRAW_HANDLER:
        bpy.types.SpaceView3D.draw_handler_remove(GL_DRAW_HANDLER, 'WINDOW')
        GL_DRAW_HANDLER = None

    for km, kmi in GL_ADDON_KEYMAPS:
        km.keymap_items.remove(kmi)
    GL_ADDON_KEYMAPS.clear()

    bpy.types.VIEW3D_MT_view_align.remove(a2c_menu_func)

    bpy.utils.unregister_class(VIEW3D_MT_align2selection)
    bpy.utils.unregister_class(VIEW3D_MT_align2cursor)
    bpy.utils.unregister_class(VIEW3D_MT_align2custom)
    bpy.utils.unregister_class(VIEW3D_MT_a2c)
    bpy.utils.unregister_class(VIEW3D_OT_a2c)
    bpy.utils.unregister_class(A2C_Preferences)


# ## MAIN test section ########################################################
if __name__ == "__main__":
    register()
