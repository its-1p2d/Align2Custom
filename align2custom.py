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
import bmesh


# ## Global data ##############################################################
# Operator idnames for keymaps shown in addon preferences (Keymap section)
A2C_KEYMAP_PREF_OPERATORS = (
    'view3d.a2c_pivot_view_drag',
    'view3d.a2c_leave_aligned_view',
)
GL_TOKEN_LOCK = False       # Locking token while rotating 3D View
# Storage for original perspective mode and rotation state for each area
# Also stores pre-alignment view (rotation, location, distance) for "Leave aligned view"
GL_VIEWPORT_STATE = {}      # Format: {area_ptr: {'original_perspective': str, 'aligned_rotation': quat, 'is_aligned': bool, 'view_rotation_before': quat, 'view_location_before': Vector, 'view_distance_before': float}}
GL_DRAW_HANDLER = None      # Draw handler for monitoring viewport changes


# ## Constants ################################################################

# Rotation dot product threshold: below this value (~2.5°) the view is
# considered rotated away from the aligned position.
A2C_ROTATION_DOT_THRESHOLD = 0.999

# Viewpoint enum items shared by all operators that accept a viewpoint argument.
A2C_VIEWPOINT_ITEMS = (
    ("TOP",     "Top view",     "", 1),
    ("BOTTOM",  "Bottom view",  "", 2),
    ("FRONT",   "Front view",   "", 3),
    ("BACK",    "Back view",    "", 4),
    ("RIGHT",   "Right view",   "", 5),
    ("LEFT",    "Left view",    "", 6),
    ("NEAREST", "Nearest view", "", 7),
)

# Pie / align mode enum items shared by ui.a2c_pie_mode and preferences.pref_default_pie_mode.
A2C_PIE_MODE_ITEMS = (
    ('CUSTOM',    'Custom',    'Align to custom transform orientation', 'OBJECT_ORIGIN',       0),
    ('CURSOR',    'Cursor',    'Align to 3D cursor orientation',        'PIVOT_CURSOR',        1),
    ('SELECTION', 'Selection', 'Align to selection orientation',        'RESTRICT_SELECT_OFF', 2),
    ('EDGE',      'Edge',      'Align to selected edge (one edge only)', 'SPLIT_HORIZONTAL',   3),
)

# Roll angles (degrees) tested when minimizing viewport roll.
A2C_ROLL_ANGLES = (0, 90, 180, 270)

# Viewpoint rotation matrices built once at load time.
A2C_VIEWPOINT_MATRICES = {
    "TOP":    mu.Matrix.Identity(3),
    "BOTTOM": mu.Matrix.Rotation(math.radians(180.0), 3, 'X'),
    "FRONT":  mu.Matrix.Rotation(math.radians(90.0), 3, 'X'),
    "BACK":   mu.Matrix.Rotation(math.radians(90.0), 3, 'X') @ mu.Matrix.Rotation(math.radians(180.0), 3, 'Y'),
    "RIGHT":  mu.Matrix.Rotation(math.radians(90.0), 3, 'X') @ mu.Matrix.Rotation(math.radians(90.0), 3, 'Y'),
    "LEFT":   mu.Matrix.Rotation(math.radians(90.0), 3, 'X') @ mu.Matrix.Rotation(math.radians(-90.0), 3, 'Y'),
}


# ## Viewport monitoring system ###############################################
def get_area_pointer(area):
    """Get a unique pointer identifier for a 3D viewport area"""
    if area and area.type == 'VIEW_3D':
        return area.as_pointer()
    return None


def store_viewport_state(area, original_perspective, aligned_rotation,
                        view_rotation_before=None, view_location_before=None, view_distance_before=None,
                        transform_orientation_before=None, object_align_before=None):
    """Store the original viewport state before alignment (for restore on leave)"""
    area_ptr = get_area_pointer(area)
    if area_ptr:
        global GL_VIEWPORT_STATE
        state = {
            'original_perspective': original_perspective,
            'aligned_rotation': aligned_rotation,
            'is_aligned': True
        }
        if view_rotation_before is not None:
            state['view_rotation_before'] = view_rotation_before.copy()
        if view_location_before is not None:
            state['view_location_before'] = view_location_before.copy()
        if view_distance_before is not None:
            state['view_distance_before'] = float(view_distance_before)
        if transform_orientation_before is not None:
            state['transform_orientation_before'] = str(transform_orientation_before)
        if object_align_before is not None:
            state['object_align_before'] = str(object_align_before)
        GL_VIEWPORT_STATE[area_ptr] = state


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
                        
                        # If the rotation has changed significantly, restore original perspective
                        if dot_product < A2C_ROTATION_DOT_THRESHOLD:
                            space.region_3d.view_perspective = state['original_perspective']
                            state['is_aligned'] = False  # Mark as no longer aligned
                            if 'transform_orientation_before' in state:
                                try:
                                    window.scene.transform_orientation_slots[0].type = state['transform_orientation_before']
                                except Exception:
                                    pass
                            if 'object_align_before' in state:
                                try:
                                    bpy.context.preferences.edit.object_align = state['object_align_before']
                                    if 'a2c_object_align_before' in window.scene:
                                        del window.scene['a2c_object_align_before']
                                except Exception:
                                    pass


def viewport_draw_handler():
    """Draw handler to monitor viewport rotation changes"""
    try:
        check_and_restore_perspective()
    except Exception:
        # Silently handle any errors to avoid disrupting the viewport
        pass


def restore_object_align_from_scene():
    """
    Restore object_align from persistent scene storage if the addon changed it
    in a previous session and never restored it (e.g. after a Blender restart).
    """
    try:
        for window in bpy.context.window_manager.windows:
            scene = window.scene
            if 'a2c_object_align_before' in scene:
                bpy.context.preferences.edit.object_align = scene['a2c_object_align_before']
                del scene['a2c_object_align_before']
                break
    except Exception:
        pass



def is_viewport_aligned(context):
    """
    Return True if the current 3D viewport is in an aligned state
    (i.e. was aligned by this addon and not rotated away since).
    When the view is maximized/unmaximized the area pointer can change;
    we detect that by matching the current view rotation to any stored state
    and migrate the state to the current area.
    """
    if not context.area or context.area.type != 'VIEW_3D':
        return False
    area_ptr = get_area_pointer(context.area)
    if not area_ptr:
        return False
    if area_ptr in GL_VIEWPORT_STATE:
        return GL_VIEWPORT_STATE[area_ptr].get('is_aligned', False)
    # Area not in state (e.g. recreated after maximize) – check if current
    # view rotation matches any stored aligned view and migrate state
    try:
        space = context.space_data
        if not space:
            return False
        current_rotation = space.region_3d.view_rotation
        for ptr, state in list(GL_VIEWPORT_STATE.items()):
            if not state.get('is_aligned'):
                continue
            if abs(current_rotation.dot(state['aligned_rotation'])) >= A2C_ROTATION_DOT_THRESHOLD:
                GL_VIEWPORT_STATE[area_ptr] = dict(state)
                del GL_VIEWPORT_STATE[ptr]
                return True
    except Exception:
        pass
    return False


def has_single_edge_selected(context):
    """Return True if in Edit Mesh mode with exactly one edge selected."""
    if context.mode != 'EDIT_MESH':
        return False
    obj = context.edit_object
    if not obj or obj.type != 'MESH':
        return False
    return obj.data.total_edge_sel == 1


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
    
    for rotation_degrees in A2C_ROLL_ANGLES:
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
# ## Operator section #########################################################


class VIEW3D_OT_a2c_pivot_view(bpy.types.Operator):
    """
    Pivot the 3D view by 90 degrees in the given direction (up, down, left, right).
    Works in the current view's local frame, regardless of how the view was aligned.
    """
    bl_idname = "view3d.a2c_pivot_view"
    bl_label = "Pivot View 90°"
    bl_options = {'REGISTER'}

    direction: bpy.props.EnumProperty(
        items=[
            ("TOP",    "Top",    "Pivot view 90° toward top",    1),
            ("BOTTOM", "Bottom", "Pivot view 90° toward bottom", 2),
            ("LEFT",   "Left",   "Pivot view 90° toward left",   3),
            ("RIGHT",  "Right",  "Pivot view 90° toward right",   4),
        ],
        name="Direction",
        default="TOP",
    )

    def execute(self, context):
        space = context.space_data
        if not space or space.type != 'VIEW_3D':
            return {'CANCELLED'}
        rv3d = space.region_3d
        view_quat = rv3d.view_rotation.copy()
        # Rotate in the view's local frame so roll is preserved:
        # local X = right, local Y = up, local Z = forward (view direction)
        if self.direction == 'LEFT':
            # Orbit left: rotate around local Y (up) by -90°
            rot_quat = mu.Quaternion((0, 1, 0), math.radians(-90))
        elif self.direction == 'RIGHT':
            rot_quat = mu.Quaternion((0, 1, 0), math.radians(90))
        elif self.direction == 'TOP':
            # Tilt up: rotate around local X (right) by -90°
            rot_quat = mu.Quaternion((1, 0, 0), math.radians(-90))
        else:  # BOTTOM
            rot_quat = mu.Quaternion((1, 0, 0), math.radians(90))
        # view_quat @ rot_quat = apply view then rotate in its local frame
        new_quat = (view_quat @ rot_quat).normalized()

        prefs = context.preferences.addons[__package__].preferences
        area_ptr = get_area_pointer(context.area)

        if prefs.pref_smooth:
            global GL_TOKEN_LOCK
            GL_TOKEN_LOCK = True
            rotation_job = thd.Thread(
                target=VIEW3D_OT_a2c.smooth_rotate,
                args=(space, view_quat, new_quat)
            )
            rotation_job.start()
        else:
            rv3d.view_rotation = new_quat

        # Keep viewport in "aligned" state so relative pie layout stays available
        if area_ptr and area_ptr in GL_VIEWPORT_STATE:
            GL_VIEWPORT_STATE[area_ptr]['aligned_rotation'] = new_quat
            GL_VIEWPORT_STATE[area_ptr]['is_aligned'] = True
        return {'FINISHED'}


# Minimum drag distance (pixels) to trigger pivot direction
PIVOT_DRAG_THRESHOLD = 15


class VIEW3D_OT_a2c_pivot_view_drag(bpy.types.Operator):
    """
    Pivot the aligned view by 90° based on Alt+MMB drag direction.
    Only works when the viewport is in aligned state (similar to view3d.view_axis).
    """
    bl_idname = "view3d.a2c_pivot_view_drag"
    bl_label = "Pivot View by Drag (Aligned)"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        if not is_viewport_aligned(context):
            return {'PASS_THROUGH'}
        self.start_x = event.mouse_x
        self.start_y = event.mouse_y
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'MIDDLEMOUSE' and event.value == 'RELEASE':
            dx = event.mouse_x - self.start_x
            dy = event.mouse_y - self.start_y
            if abs(dx) < PIVOT_DRAG_THRESHOLD and abs(dy) < PIVOT_DRAG_THRESHOLD:
                return {'CANCELLED'}
            if abs(dx) >= abs(dy):
                # Drag right (dx > 0) = pivot LEFT; drag left = pivot RIGHT
                direction = 'LEFT' if dx > 0 else 'RIGHT'
            else:
                # Drag up (dy > 0) = pivot BOTTOM; drag down = pivot TOP (inverted from widget)
                direction = 'BOTTOM' if dy > 0 else 'TOP'
            bpy.ops.view3d.a2c_pivot_view(direction=direction)
            return {'FINISHED'}
        if event.type in ('ESC', 'RIGHTMOUSE'):
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


class VIEW3D_OT_a2c_leave_aligned_view(bpy.types.Operator):
    """
    Restore the view to its state from before the last alignment.
    Only available when the viewport is in aligned state.
    """
    bl_idname = "view3d.a2c_leave_aligned_view"
    bl_label = "Leave Aligned View"
    bl_options = {'REGISTER'}

    def execute(self, context):
        if not context.area or context.area.type != 'VIEW_3D':
            return {'CANCELLED'}
        area_ptr = get_area_pointer(context.area)
        if not area_ptr or area_ptr not in GL_VIEWPORT_STATE:
            return {'CANCELLED'}
        state = GL_VIEWPORT_STATE[area_ptr]
        if not state.get('is_aligned'):
            return {'CANCELLED'}
        if 'view_rotation_before' not in state or 'view_location_before' not in state:
            return {'CANCELLED'}
        space = context.space_data
        rv3d = space.region_3d
        current_quat = rv3d.view_rotation.copy()
        target_quat = state['view_rotation_before'].copy()

        # Restore transform orientation and object align immediately
        if 'transform_orientation_before' in state:
            try:
                context.scene.transform_orientation_slots[0].type = state['transform_orientation_before']
            except Exception:
                pass
        if 'object_align_before' in state:
            try:
                context.preferences.edit.object_align = state['object_align_before']
                if 'a2c_object_align_before' in context.scene:
                    del context.scene['a2c_object_align_before']
            except Exception:
                pass

        prefs = context.preferences.addons[__package__].preferences
        if prefs.pref_smooth:
            global GL_TOKEN_LOCK
            GL_TOKEN_LOCK = True

            def on_leave_complete(space):
                space.region_3d.view_location = state['view_location_before'].copy()
                space.region_3d.view_distance = state['view_distance_before']
                space.region_3d.view_perspective = state['original_perspective']
                state['is_aligned'] = False

            rotation_job = thd.Thread(
                target=VIEW3D_OT_a2c.smooth_rotate,
                args=(space, current_quat, target_quat, on_leave_complete)
            )
            rotation_job.start()
        else:
            rv3d.view_rotation = target_quat
            rv3d.view_location = state['view_location_before'].copy()
            rv3d.view_distance = state['view_distance_before']
            rv3d.view_perspective = state['original_perspective']
            state['is_aligned'] = False
        return {'FINISHED'}


class VIEW3D_OT_a2c_roll_view(bpy.types.Operator):
    """
    Roll the 3D view by an angle (radians), enforce orthographic view,
    and update the aligned state so the addon still considers the view aligned.
    """
    bl_idname = "view3d.a2c_roll_view"
    bl_label = "Roll View (Aligned)"
    bl_options = {'REGISTER'}

    angle: bpy.props.FloatProperty(
        name="Angle",
        description="Roll angle in radians",
        default=0.0,
        unit='ROTATION',
    )

    def execute(self, context):
        space = context.space_data
        if not space or space.type != 'VIEW_3D':
            return {'CANCELLED'}
        rv3d = space.region_3d
        view_quat = rv3d.view_rotation.copy()
        # Roll: rotate around view's forward axis (local Z)
        new_quat = (view_quat @ mu.Quaternion((0, 0, 1), self.angle)).normalized()

        prefs = context.preferences.addons[__package__].preferences
        area_ptr = get_area_pointer(context.area)

        if prefs.pref_smooth:
            global GL_TOKEN_LOCK
            GL_TOKEN_LOCK = True
            rotation_job = thd.Thread(
                target=VIEW3D_OT_a2c.smooth_rotate,
                args=(space, view_quat, new_quat)
            )
            rotation_job.start()
        else:
            rv3d.view_rotation = new_quat

        rv3d.view_perspective = 'ORTHO'
        if area_ptr and area_ptr in GL_VIEWPORT_STATE:
            GL_VIEWPORT_STATE[area_ptr]['aligned_rotation'] = new_quat
            GL_VIEWPORT_STATE[area_ptr]['is_aligned'] = True
        return {'FINISHED'}


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

    prop_align_mode: bpy.props.EnumProperty(items=ALIGN_MODE_ITEMS,
                                            name="Align mode",
                                            default="CUSTOM")
    prop_viewpoint: bpy.props.EnumProperty(items=A2C_VIEWPOINT_ITEMS,
                                           name="Point of view",
                                           default="TOP")

    SMOOTH_ROT_STEP = 0.02
    SMOOTH_ROT_DURATION = 0.24

    @staticmethod
    def smooth_rotate(space, quat_begin, quat_end, on_complete=None):
        """
        Rotate the 3D view smoothly between the quaternions 'quat_begin' and
        'quat_end'. If on_complete is given, call it with (space,) at the end.
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
            # Ensure ORTHO view is set after rotation completes (caller may overwrite in on_complete)
            space.region_3d.view_perspective = 'ORTHO'
            if on_complete:
                on_complete(space)

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

            # Store original perspective and full view state before alignment (for "Leave aligned view")
            rv3d = space.region_3d
            original_perspective = rv3d.view_perspective
            view_rotation_before = rv3d.view_rotation.copy()
            view_location_before = rv3d.view_location.copy()
            view_distance_before = rv3d.view_distance

            # Determine the base matrix first (needed for NEAREST calculation)
            if self.prop_align_mode == 'CURSOR':
                base_matrix = scene.cursor.matrix.to_3x3()
            else:
                # Both CUSTOM and SELECTION modes use the custom orientation
                base_matrix = co.matrix.copy()

            # Compute the rotation matrix according to the desired viewpoint
            if self.prop_viewpoint == "NEAREST":
                # Find the nearest viewpoint based on VIEW DIRECTION only (ignoring roll)
                current_quat = space.region_3d.view_rotation
                current_view_matrix = current_quat.to_matrix()
                current_view_direction = -current_view_matrix.col[2]  # -Z axis is view direction

                max_dot = -float('inf')
                best_viewpoint = "TOP"

                for viewpoint_name, viewpoint_rot in A2C_VIEWPOINT_MATRICES.items():
                    target_view_direction = -(base_matrix @ viewpoint_rot).col[2]
                    dot = current_view_direction.dot(target_view_direction)
                    if dot > max_dot:
                        max_dot = dot
                        best_viewpoint = viewpoint_name

                rot_matrix = A2C_VIEWPOINT_MATRICES[best_viewpoint]
            elif self.prop_viewpoint in A2C_VIEWPOINT_MATRICES:
                rot_matrix = A2C_VIEWPOINT_MATRICES[self.prop_viewpoint]
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
            transform_orientation_before = None
            object_align_before = None
            if prefs.pref_use_view_orientation_in_aligned_view:
                transform_orientation_before = scene.transform_orientation_slots[0].type
                try:
                    object_align_before = context.preferences.edit.object_align
                except Exception:
                    pass
            store_viewport_state(
                context.area, original_perspective, final_quat,
                view_rotation_before=view_rotation_before,
                view_location_before=view_location_before,
                view_distance_before=view_distance_before,
                transform_orientation_before=transform_orientation_before,
                object_align_before=object_align_before
            )

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
            if prefs.pref_use_view_orientation_in_aligned_view:
                scene.transform_orientation_slots[0].type = 'VIEW'
                try:
                    # Persist the before-value in the scene so it survives a Blender restart
                    scene['a2c_object_align_before'] = context.preferences.edit.object_align
                    context.preferences.edit.object_align = 'VIEW'
                except Exception:
                    pass

        else:
            # If we couldn't proceed but created a temp orientation, clean it up
            if temp_orientation_created:
                try:
                    bpy.ops.transform.delete_orientation()
                except RuntimeError:
                    pass

        return {'FINISHED'}


# ## Edge alignment operator ##################################################

class VIEW3D_OT_a2c_align_to_edge(bpy.types.Operator):
    """Align the view so the selected edge appears perfectly horizontal.
Temporarily moves the 3D Cursor to the edge midpoint and orients it
along the edge, aligns the view, then restores the cursor."""
    bl_idname = "view3d.a2c_align_to_edge"
    bl_label = "Align View to Edge"
    bl_options = {'REGISTER'}

    prop_viewpoint: bpy.props.EnumProperty(
        items=A2C_VIEWPOINT_ITEMS,
        name="Point of view",
        default="TOP",
    )

    @classmethod
    def poll(cls, context):
        if not context.space_data or context.space_data.type != 'VIEW_3D':
            return False
        if context.mode != 'EDIT_MESH':
            return False
        obj = context.edit_object
        if not obj or obj.type != 'MESH':
            return False
        return obj.data.total_edge_sel == 1

    def execute(self, context):
        scene = context.scene
        space = context.space_data
        obj = context.edit_object

        # Save full cursor state so we can restore it after aligning
        saved_location = scene.cursor.location.copy()
        saved_rotation_mode = scene.cursor.rotation_mode
        saved_rotation_quat = scene.cursor.rotation_quaternion.copy()
        saved_rotation_euler = scene.cursor.rotation_euler.copy()
        saved_rotation_axis_angle = list(scene.cursor.rotation_axis_angle)

        try:
            bm = bmesh.from_edit_mesh(obj.data)
            e = next((ed for ed in bm.edges if ed.select), None)
            if e is None:
                return {'CANCELLED'}

            # Edge midpoint in world space
            mid_world = obj.matrix_world @ ((e.verts[0].co + e.verts[1].co) / 2)

            # Build an orientation matrix so the edge is the local X axis and
            # lies flat (horizontal) when the view is snapped to TOP.
            # cam  = view Z axis in world space (points toward viewer)
            # ed   = edge direction in world space (becomes cursor local X)
            # perp = vector perpendicular to both edge and cam (cursor local Y)
            # cam2 = recomputed cam-like direction perpendicular to edge (cursor local Z)
            vr = space.region_3d.view_rotation
            cam = (vr @ mu.Vector((0, 0, 1))).normalized()
            ed_vec = (obj.matrix_world.to_3x3() @ (e.verts[1].co - e.verts[0].co)).normalized()

            # Guard against degenerate edge (zero length) or edge parallel to view
            perp = ed_vec.cross(cam)
            if perp.length < 1e-6:
                self.report({'WARNING'}, "Edge is parallel to the view direction; cannot align")
                return {'CANCELLED'}
            perp = perp.normalized()
            cam2 = ed_vec.cross(perp).normalized()

            m = mu.Matrix([ed_vec, perp, cam2]).transposed()

            # Temporarily place cursor at edge midpoint with computed orientation
            scene.cursor.location = mid_world
            scene.cursor.rotation_mode = 'QUATERNION'
            scene.cursor.rotation_quaternion = m.to_quaternion()

            # Align view: cursor + chosen viewpoint (TOP = edge horizontal)
            bpy.ops.view3d.a2c(prop_align_mode='CURSOR', prop_viewpoint=self.prop_viewpoint)

        finally:
            # Restore cursor to its original state regardless of what happened
            scene.cursor.rotation_mode = saved_rotation_mode
            if saved_rotation_mode == 'QUATERNION':
                scene.cursor.rotation_quaternion = saved_rotation_quat
            elif saved_rotation_mode == 'AXIS_ANGLE':
                scene.cursor.rotation_axis_angle = saved_rotation_axis_angle
            else:
                scene.cursor.rotation_euler = saved_rotation_euler
            scene.cursor.location = saved_location

        return {'FINISHED'}


# ## Blender registration section #############################################
def register():
    """
    Module register function called by the main package register function
    """
    global GL_DRAW_HANDLER

    # Restore object_align if the addon changed it in a previous session
    # (e.g. Blender was closed while in aligned view and the runtime state was lost)
    restore_object_align_from_scene()

    bpy.utils.register_class(VIEW3D_OT_a2c_pivot_view_drag)
    bpy.utils.register_class(VIEW3D_OT_a2c_leave_aligned_view)
    bpy.utils.register_class(VIEW3D_OT_a2c_roll_view)
    bpy.utils.register_class(VIEW3D_OT_a2c_pivot_view)
    bpy.utils.register_class(VIEW3D_OT_a2c)
    bpy.utils.register_class(VIEW3D_OT_a2c_align_to_edge)

    # Register the viewport draw handler
    GL_DRAW_HANDLER = bpy.types.SpaceView3D.draw_handler_add(
        viewport_draw_handler, (), 'WINDOW', 'POST_PIXEL'
    )


def unregister():
    """
    Module unregister function called by the main package register function
    """
    global GL_VIEWPORT_STATE, GL_DRAW_HANDLER

    # Restore object_align if we changed it and the user is still in aligned view
    for state in GL_VIEWPORT_STATE.values():
        if state.get('is_aligned') and 'object_align_before' in state:
            try:
                bpy.context.preferences.edit.object_align = state['object_align_before']
            except Exception:
                pass
            break
    restore_object_align_from_scene()

    # Clean up global state
    GL_VIEWPORT_STATE.clear()

    # Remove the viewport draw handler
    if GL_DRAW_HANDLER:
        bpy.types.SpaceView3D.draw_handler_remove(GL_DRAW_HANDLER, 'WINDOW')
        GL_DRAW_HANDLER = None

    bpy.utils.unregister_class(VIEW3D_OT_a2c_align_to_edge)
    bpy.utils.unregister_class(VIEW3D_OT_a2c)
    bpy.utils.unregister_class(VIEW3D_OT_a2c_roll_view)
    bpy.utils.unregister_class(VIEW3D_OT_a2c_leave_aligned_view)
    bpy.utils.unregister_class(VIEW3D_OT_a2c_pivot_view_drag)
    bpy.utils.unregister_class(VIEW3D_OT_a2c_pivot_view)


# ## MAIN test section ########################################################
if __name__ == "__main__":
    register()
