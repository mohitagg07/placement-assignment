"""
A utility module for the PCB Component Placement coding assignment.

This module provides functions to:
1.  Validate a given component placement against all hard constraints.
2.  Calculate a score for a valid placement based on soft constraints.
3.  Generate a plot to visualize a placement and its constraints.

A candidate should import these functions into their own solver script to check
the correctness and quality of their generated solution.

Expected Placement Dictionary Format:
{
    'COMPONENT_NAME': {'x': float, 'y': float, 'w': float, 'h': float},
    ...
}
"""
import time
import math
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# --- Assignment Constants (Part of the problem definition) ---
BOARD_DIMS = (50, 50)
PROXIMITY_RADIUS = 10.0
CENTER_OF_MASS_RADIUS = 2.0
KEEPOUT_ZONE_DIMS = (10, 20)  # 10 wide, 15 inward
VALIDATION_TIME_LIMIT = 2 # Validation should be extremely fast

# --- Geometric Helper Functions (Internal use) ---
def _get_center(comp):
    """Calculates the center coordinates of a component."""
    return (comp['x'] + comp['w'] / 2, comp['y'] + comp['h'] / 2)

def _distance(p1, p2):
    """Calculates the Euclidean distance between two points."""
    return math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)

# --- Public Utility Functions for Candidates ---

def validate_placement(placement):
    """
    Validates a component placement against all hard constraints.

    This function checks each rule from the assignment specification and prints
    a detailed report of which rules passed or failed.

    Args:
        placement (dict): A dictionary representing the component placement.
            Keys should be the component names (e.g., 'USB_CONNECTOR').
            Values should be dictionaries with 'x', 'y', 'w', 'h' keys.

    Returns:
        bool: True if the placement satisfies all hard constraints, False otherwise.
    """
    print("--- Running Detailed Hard Constraint Validation ---")
    results = {}
    
    # Check for presence of all required components
    required_keys = ['USB_CONNECTOR', 'MICROCONTROLLER', 'CRYSTAL', 
                     'MIKROBUS_CONNECTOR_1', 'MIKROBUS_CONNECTOR_2']
    if not all(key in placement for key in required_keys):
        print("❌ FAILED: The placement dictionary is missing one or more required components.")
        return False

    # Rule 5: Boundary Constraint
    all_in_bounds = True
    for name, comp in placement.items():
        if not (comp['x'] >= 0 and comp['y'] >= 0 and
                comp['x'] + comp['w'] <= BOARD_DIMS[0] and
                comp['y'] + comp['h'] <= BOARD_DIMS[1]):
            all_in_bounds = False
            break
    results["Boundary Constraint"] = (all_in_bounds, "")

    # Rule 4: No Overlapping
    items = list(placement.items())
    overlap_found = False
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            c1, c2 = items[i][1], items[j][1]
            if not (c1['x'] + c1['w'] <= c2['x'] or c1['x'] >= c2['x'] + c2['w'] or
                    c1['y'] + c1['h'] <= c2['y'] or c1['y'] >= c2['y'] + c2['h']):
                overlap_found = True
                break
        if overlap_found: break
    results["No Overlapping"] = (not overlap_found, "")
    
    # Rule 1: Edge Placement
    edge_names = ['USB_CONNECTOR', 'MIKROBUS_CONNECTOR_1', 'MIKROBUS_CONNECTOR_2']
    all_on_edge = True
    for name in edge_names:
        comp = placement[name]
        if not (comp['x'] == 0 or comp['y'] == 0 or
                comp['x'] + comp['w'] == BOARD_DIMS[0] or comp['y'] + comp['h'] == BOARD_DIMS[1]):
            all_on_edge = False
            break
    results["Edge Placement"] = (all_on_edge, "")

    # Rule 2: Parallel Placement
    mb1, mb2 = placement['MIKROBUS_CONNECTOR_1'], placement['MIKROBUS_CONNECTOR_2']
    is_parallel = False
    if mb1['w'] == mb2['w']:  # Same orientation
        on_opp_v = (mb1['x'] == 0 and mb2['x'] + mb2['w'] == BOARD_DIMS[0]) or \
                   (mb1['x'] + mb1['w'] == BOARD_DIMS[0] and mb2['x'] == 0)
        on_opp_h = (mb1['y'] == 0 and mb2['y'] + mb2['h'] == BOARD_DIMS[1]) or \
                   (mb1['y'] + mb1['h'] == BOARD_DIMS[1] and mb2['y'] == 0)
        if on_opp_v or on_opp_h:
            is_parallel = True
    results["Parallel Placement"] = (is_parallel, "")

    # Rule 3: Proximity Constraint
    dist = _distance(_get_center(placement['CRYSTAL']), _get_center(placement['MICROCONTROLLER']))
    results["Proximity Constraint"] = (dist <= PROXIMITY_RADIUS, f"Actual distance: {dist:.2f} (Limit: {PROXIMITY_RADIUS})")

    # Rule 6: Global Balance Constraint
    board_center = (BOARD_DIMS[0] / 2, BOARD_DIMS[1] / 2)
    com_x = sum(_get_center(c)[0] for c in placement.values()) / len(placement)
    com_y = sum(_get_center(c)[1] for c in placement.values()) / len(placement)
    com_dist = _distance((com_x, com_y), board_center)
    results["Global Balance"] = (com_dist <= CENTER_OF_MASS_RADIUS, f"CoM dist from center: {com_dist:.2f} (Limit: {CENTER_OF_MASS_RADIUS})")

    # Rule 7: Crystal Keep-Out Zone
    usb, crystal, micro = placement['USB_CONNECTOR'], placement['CRYSTAL'], placement['MICROCONTROLLER']
    zone_w, zone_h_inward = KEEPOUT_ZONE_DIMS
    usb_cx, usb_cy = _get_center(usb)
    if usb['y'] == 0: zone = {'x': usb_cx - zone_w / 2, 'y': 0, 'w': zone_w, 'h': zone_h_inward}
    elif usb['y'] + usb['h'] == BOARD_DIMS[1]: zone = {'x': usb_cx - zone_w / 2, 'y': BOARD_DIMS[1] - zone_h_inward, 'w': zone_w, 'h': zone_h_inward}
    elif usb['x'] == 0: zone = {'x': 0, 'y': usb_cy - zone_w / 2, 'w': zone_h_inward, 'h': zone_w}
    else: zone = {'x': BOARD_DIMS[0] - zone_h_inward, 'y': usb_cy - zone_w / 2, 'w': zone_h_inward, 'h': zone_w}
    p1, p2 = _get_center(crystal), _get_center(micro)
    def ccw(A,B,C): return (C[1]-A[1]) * (B[0]-A[0]) > (B[1]-A[1]) * (C[0]-A[0])
    def intersect(A,B,C,D): return ccw(A,C,D) != ccw(B,C,D) and ccw(A,B,C) != ccw(A,B,D)
    tl, tr, bl, br = (zone['x'], zone['y']), (zone['x'] + zone['w'], zone['y']), (zone['x'], zone['y'] + zone['h']), (zone['x'] + zone['w'], zone['y'] + zone['h'])
    intersects = (intersect(p1, p2, tl, tr) or intersect(p1, p2, tr, br) or intersect(p1, p2, br, bl) or intersect(p1, p2, bl, tl))
    results["Keep-Out Zone"] = (not intersects, "Path is clear" if not intersects else "Path is obstructed")

    # Print Report
    all_valid = True
    for rule, (is_valid, msg) in results.items():
        status = "✅ PASSED" if is_valid else "❌ FAILED"
        print(f"{rule:<22}: {status} {msg}")
        if not is_valid: all_valid = False
    
    return all_valid

def score_placement(placement):
    """
    Calculates a score for a placement based on soft constraints.

    A lower score is better. The score is a combination of the total
    area of the layout's bounding box (compactness) and the distance
    of the microcontroller from the board's center (centrality).

    Note: This function should ideally be called only for placements that
    have already passed validation.

    Args:
        placement (dict): A valid component placement dictionary.

    Returns:
        float: The calculated total score for the placement.
    """
    print("\n--- Calculating Placement Score (Lower is Better) ---")
    min_x = min(c['x'] for c in placement.values())
    max_x = max(c['x'] + c['w'] for c in placement.values())
    min_y = min(c['y'] for c in placement.values())
    max_y = max(c['y'] + c['h'] for c in placement.values())
    bounding_box_area = (max_x - min_x) * (max_y - min_y)
    
    board_center = (BOARD_DIMS[0] / 2, BOARD_DIMS[1] / 2)
    micro_center = _get_center(placement['MICROCONTROLLER'])
    centrality_score = _distance(micro_center, board_center)
    
    total_score = bounding_box_area + (centrality_score * 10) # Weight centrality
    print(f"Compactness Score (Bounding Box Area): {bounding_box_area:.2f}")
    print(f"Centrality Score (uC dist from center): {centrality_score:.2f}")
    print(f"-------------------------------------------")
    print(f"Total Combined Score: {total_score:.2f}")
    print(f"-------------------------------------------")
    return total_score

def plot_placement(placement):
    """
    Generates a matplotlib plot to visualize the component placement.

    This function displays the board, grid, components, and visual indicators
    for the proximity and keep-out zone constraints. Execution will be
    blocked until the plot window is closed.

    Args:
        placement (dict): A component placement dictionary to visualize.
    """
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.set_xlim(0, BOARD_DIMS[0])
    ax.set_ylim(0, BOARD_DIMS[1])
    ax.set_xticks(range(0, BOARD_DIMS[0] + 1, 5))
    ax.set_yticks(range(0, BOARD_DIMS[1] + 1, 5))
    ax.grid(True, linestyle='--', color='gray', alpha=0.5)
    ax.set_aspect('equal', adjustable='box')
    ax.invert_yaxis()
    ax.set_title("PCB Component Placement Solution")
    
    colors = {'USB_CONNECTOR': '#e74c3c', 'MICROCONTROLLER': '#3498db', 'CRYSTAL': '#f39c12',
              'MIKROBUS_CONNECTOR_1': '#9b59b6', 'MIKROBUS_CONNECTOR_2': '#8e44ad'}
    labels = {'USB_CONNECTOR': 'USB', 'MICROCONTROLLER': 'μC', 'CRYSTAL': 'XTAL',
              'MIKROBUS_CONNECTOR_1': 'MB1', 'MIKROBUS_CONNECTOR_2': 'MB2'}

    for name, comp in placement.items():
        rect = patches.Rectangle((comp['x'], comp['y']), comp['w'], comp['h'],
                                 linewidth=1, edgecolor='black', facecolor=colors[name])
        ax.add_patch(rect)
        ax.text(comp['x'] + comp['w'] / 2, comp['y'] + comp['h'] / 2, labels[name],
                color='white', ha='center', va='center', fontweight='bold')
    
    uc_center = _get_center(placement['MICROCONTROLLER'])
    circle = patches.Circle(uc_center, PROXIMITY_RADIUS, fill=True, color='#f39c12', alpha=0.1,
                            linestyle='--', lw=2)
    ax.add_patch(circle)
    
    usb = placement['USB_CONNECTOR']
    zone_w, zone_h_inward = KEEPOUT_ZONE_DIMS
    usb_cx, usb_cy = _get_center(usb)
    if usb['y'] == 0: zone_props = {'xy': (usb_cx-zone_w/2, 0), 'w': zone_w, 'h': zone_h_inward}
    elif usb['y']+usb['h']==BOARD_DIMS[1]: zone_props = {'xy': (usb_cx-zone_w/2, BOARD_DIMS[1]-zone_h_inward), 'w': zone_w, 'h': zone_h_inward}
    elif usb['x'] == 0: zone_props = {'xy': (0, usb_cy-zone_w/2), 'w': zone_h_inward, 'h': zone_w}
    else: zone_props = {'xy': (BOARD_DIMS[0]-zone_h_inward, usb_cy-zone_w/2), 'w': zone_h_inward, 'h': zone_w}
    keepout = patches.Rectangle(zone_props['xy'], zone_props['w'], zone_props['h'], fill=True, color='#e74c3c', alpha=0.15, linestyle='--', lw=2)
    ax.add_patch(keepout)
    
    xtal_center = _get_center(placement['CRYSTAL'])
    ax.plot([xtal_center[0], uc_center[0]], [xtal_center[1], uc_center[1]], 'k--')
    
    plt.show()


if __name__ == '__main__':
    """
    Example usage of the utility functions.
    
    This block demonstrates how a candidate would use this module to test their
    own generated placements.
    """
    # --- Start of Appended Time Check ---
    start_time = time.perf_counter()

    # --- Example 1: A valid placement ---
    print("--- DEMO 1: TESTING A VALID PLACEMENT ---")
    sample_valid_placement = {
        'USB_CONNECTOR':        {'x': 20, 'y': 45, 'w': 5, 'h': 5},
        'MIKROBUS_CONNECTOR_1': {'x': 0, 'y': 15, 'w': 5, 'h': 15},
        'MIKROBUS_CONNECTOR_2': {'x': 45, 'y': 15, 'w': 5, 'h': 15},
        'MICROCONTROLLER':      {'x': 22, 'y': 22, 'w': 5, 'h': 5},
        'CRYSTAL':              {'x': 25, 'y': 14, 'w': 5, 'h': 5},
    }

    is_valid = validate_placement(sample_valid_placement)
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    
    print("\n--- Performance Report for Validation ---")
    print(f"Validation function finished in: {elapsed_time:.6f} seconds")
    if elapsed_time <= VALIDATION_TIME_LIMIT:
        print(f"✅ PERFORMANCE PASSED (Validation is fast enough)")
    else:
        print(f"❌ PERFORMANCE FAILED (Validation is too slow)")
    print("---------------------------------------")
    if is_valid:
        print("\n✅ This placement is fully valid.")
        score_placement(sample_valid_placement)
        plot_placement(sample_valid_placement)
    else:
        print("\n❌ This placement is INVALID.")
        score_placement(sample_valid_placement)
        plot_placement(sample_valid_placement)

    print("\n" + "="*50 + "\n")



