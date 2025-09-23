"""
placement_solver.py
Algorithmic PCB component placer for the assignment.

- Algorithm:
  1. Place edge-constrained components first:
     - Place MIKROBUS_CONNECTOR_1 on the left edge (vertical orientation)
     - Place MIKROBUS_CONNECTOR_2 on the right edge (vertical orientation)
     - Place USB_CONNECTOR on the bottom edge (centered horizontally by default)
  2. For MICROCONTROLLER and CRYSTAL:
     - Search microcontroller positions on a prioritized grid (center-first spiral-like ordering).
     - For each microcontroller position, search CRYSTAL positions in the circle of radius PROXIMITY_RADIUS
       around microcontroller (grid steps = 1).
     - For each candidate pair, check:
         - No overlap with existing edge components
         - Crystal-Microcontroller line does not cross USB keep-out zone
         - Global center of mass within tolerance
         - Boundary constraints
     - Score candidates and keep the best (lowest total score using same scoring formula).
  3. Output JSON placement, plot PNG, and a self-score text file.

Usage:
    python placement_solver.py

This file writes:
 - my_algorithmic_placement.json
 - placement_snapshot_algo.png
 - self_score_algo.txt
"""

import json
import math
import time
import os
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# Assignment constants (same as checker)
BOARD_DIMS = (50, 50)
PROXIMITY_RADIUS = 10.0
CENTER_OF_MASS_RADIUS = 2.0
KEEPOUT_ZONE_DIMS = (10, 20)  # width (across), depth inward
GRID_STEP = 1  # 1-unit grid
VALIDATION_TIME_LIMIT = 2.0

# Component sizes (assignment)
SIZES = {
    'USB_CONNECTOR': (5, 5),
    'MICROCONTROLLER': (5, 5),
    'CRYSTAL': (5, 5),
    'MIKROBUS_CONNECTOR_1': (5, 15),
    'MIKROBUS_CONNECTOR_2': (5, 15),
}

# Helper geometry functions
def center_of(comp):
    return (comp['x'] + comp['w'] / 2.0, comp['y'] + comp['h'] / 2.0)

def distance(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])

def bbox_overlap(a, b):
    return not (a['x'] + a['w'] <= b['x'] or b['x'] + b['w'] <= a['x'] or
                a['y'] + a['h'] <= b['y'] or b['y'] + b['h'] <= a['y'])

def in_bounds(comp):
    return (comp['x'] >= 0 and comp['y'] >= 0 and
            comp['x'] + comp['w'] <= BOARD_DIMS[0] and
            comp['y'] + comp['h'] <= BOARD_DIMS[1])

def line_intersects_rect(p1, p2, rect):
    # rect defined by x,y,w,h
    # check if line segment p1-p2 intersects any of the four rectangle edges
    def ccw(A,B,C):
        return (C[1]-A[1]) * (B[0]-A[0]) > (B[1]-A[1]) * (C[0]-A[0])
    def intersect(A,B,C,D):
        return ccw(A,C,D) != ccw(B,C,D) and ccw(A,B,C) != ccw(A,B,D)
    tl = (rect['x'], rect['y'])
    tr = (rect['x'] + rect['w'], rect['y'])
    bl = (rect['x'], rect['y'] + rect['h'])
    br = (rect['x'] + rect['w'], rect['y'] + rect['h'])
    return (intersect(p1,p2,tl,tr) or intersect(p1,p2,tr,br) or
            intersect(p1,p2,br,bl) or intersect(p1,p2,bl,tl))

def compute_keepout_zone(usb):
    zone_w, zone_depth = KEEPOUT_ZONE_DIMS
    usb_cx, usb_cy = center_of(usb)
    # Determine which edge USB touches and build rectangle going inward
    if usb['y'] == 0:
        return {'x': usb_cx - zone_w/2, 'y': 0, 'w': zone_w, 'h': zone_depth}
    if usb['y'] + usb['h'] == BOARD_DIMS[1]:
        return {'x': usb_cx - zone_w/2, 'y': BOARD_DIMS[1] - zone_depth, 'w': zone_w, 'h': zone_depth}
    if usb['x'] == 0:
        return {'x': 0, 'y': usb_cy - zone_w/2, 'w': zone_depth, 'h': zone_w}
    # right edge
    return {'x': BOARD_DIMS[0] - zone_depth, 'y': usb_cy - zone_w/2, 'w': zone_depth, 'h': zone_w}

def compute_score(placement):
    # same scoring as checker: bounding box area + 10 * distance(micro,board_center)
    min_x = min(c['x'] for c in placement.values())
    max_x = max(c['x'] + c['w'] for c in placement.values())
    min_y = min(c['y'] for c in placement.values())
    max_y = max(c['y'] + c['h'] for c in placement.values())
    bounding_box_area = (max_x - min_x) * (max_y - min_y)
    board_center = (BOARD_DIMS[0]/2.0, BOARD_DIMS[1]/2.0)
    micro_center = center_of(placement['MICROCONTROLLER'])
    centrality_score = distance(micro_center, board_center)
    total = bounding_box_area + 10.0 * centrality_score
    return total, bounding_box_area, centrality_score

# Algorithmic placer
def place_edge_components():
    """
    Place MIKROBUS connectors and USB deterministically at edges,
    but the exact positions (y offsets) are chosen algorithmically.
    Strategy:
      - Place MB1 on left edge with top at 10 units from top (but ensure in bounds)
      - Place MB2 on right edge mirrored to MB1
      - Place USB on bottom edge centered horizontally, but we can shift horizontally later if needed
    """
    mb_w, mb_h = SIZES['MIKROBUS_CONNECTOR_1']
    usb_w, usb_h = SIZES['USB_CONNECTOR']

    # place MB1 left edge, vertically centered near upper-middle area
    mb1_x = 0
    mb1_y = 10
    # ensure in bounds
    mb1_y = min(max(0, mb1_y), BOARD_DIMS[1] - mb_h)

    # place MB2 on right edge (opposite), same y to keep parallel
    mb2_x = BOARD_DIMS[0] - mb_w
    mb2_y = mb1_y

    # place USB on bottom edge, centered horizontally
    usb_x = (BOARD_DIMS[0] - usb_w) / 2.0
    usb_y = BOARD_DIMS[1] - usb_h

    placement = {}
    placement['MIKROBUS_CONNECTOR_1'] = {'x': mb1_x, 'y': mb1_y, 'w': mb_w, 'h': mb_h}
    placement['MIKROBUS_CONNECTOR_2'] = {'x': mb2_x, 'y': mb2_y, 'w': mb_w, 'h': mb_h}
    placement['USB_CONNECTOR'] = {'x': usb_x, 'y': usb_y, 'w': usb_w, 'h': usb_h}
    return placement

def validate_full(placement):
    """
    Re-implements same checks as provided checker to be sure.
    Returns (valid_bool, dict_of_results)
    """
    results = {}
    # Required keys
    required_keys = ['USB_CONNECTOR', 'MICROCONTROLLER', 'CRYSTAL', 'MIKROBUS_CONNECTOR_1', 'MIKROBUS_CONNECTOR_2']
    if not all(k in placement for k in required_keys):
        return False, {'missing': True}

    # Boundary
    all_in_bounds = all(in_bounds(c) for c in placement.values())
    results['Boundary Constraint'] = (all_in_bounds, '')

    # No overlap
    items = list(placement.items())
    overlap = False
    for i in range(len(items)):
        for j in range(i+1, len(items)):
            if bbox_overlap(items[i][1], items[j][1]):
                overlap = True
                break
        if overlap:
            break
    results['No Overlapping'] = (not overlap, '')

    # Edge placement
    edge_names = ['USB_CONNECTOR', 'MIKROBUS_CONNECTOR_1', 'MIKROBUS_CONNECTOR_2']
    all_on_edge = True
    for name in edge_names:
        comp = placement[name]
        touches = (comp['x'] == 0 or comp['y'] == 0 or
                   comp['x'] + comp['w'] == BOARD_DIMS[0] or
                   comp['y'] + comp['h'] == BOARD_DIMS[1])
        if not touches:
            all_on_edge = False
            break
    results['Edge Placement'] = (all_on_edge, '')

    # Parallel placement
    mb1 = placement['MIKROBUS_CONNECTOR_1']; mb2 = placement['MIKROBUS_CONNECTOR_2']
    is_parallel = (mb1['w'] == mb2['w']) and ((mb1['x'] == 0 and mb2['x'] + mb2['w'] == BOARD_DIMS[0]) or (mb1['x'] + mb1['w'] == BOARD_DIMS[0] and mb2['x'] == 0) or (mb1['y'] == 0 and mb2['y'] + mb2['h'] == BOARD_DIMS[1]) or (mb1['y'] + mb1['h'] == BOARD_DIMS[1] and mb2['y'] == 0))
    results['Parallel Placement'] = (is_parallel, '')

    # Proximity
    dist = distance(center_of(placement['CRYSTAL']), center_of(placement['MICROCONTROLLER']))
    results['Proximity Constraint'] = (dist <= PROXIMITY_RADIUS, f"Actual: {dist:.2f}")

    # Global balance
    centers = [center_of(c) for c in placement.values()]
    com_x = sum(c[0] for c in centers) / len(centers)
    com_y = sum(c[1] for c in centers) / len(centers)
    com_dist = distance((com_x, com_y), (BOARD_DIMS[0]/2.0, BOARD_DIMS[1]/2.0))
    results['Global Balance'] = (com_dist <= CENTER_OF_MASS_RADIUS, f"CoM dist: {com_dist:.2f}")

    # Keep-out
    usb = placement['USB_CONNECTOR']
    zone = compute_keepout_zone(usb)
    intersects = line_intersects_rect(center_of(placement['CRYSTAL']), center_of(placement['MICROCONTROLLER']), zone)
    results['Keep-Out Zone'] = (not intersects, "clear" if not intersects else "intersects")

    # combine
    all_ok = all(item[0] for item in results.values())
    return all_ok, results

def prioritized_positions(center=(BOARD_DIMS[0]/2, BOARD_DIMS[1]/2)):
    """Yield grid positions prioritized by proximity to center (spiral-ish)"""
    cx, cy = int(center[0]), int(center[1])
    maxr = max(BOARD_DIMS)
    yield (cx, cy)
    for r in range(1, maxr):
        # iterate square ring
        for dx in range(-r, r+1):
            for dy in (-r, r):
                x = cx + dx
                y = cy + dy
                if 0 <= x <= BOARD_DIMS[0]-SIZES['MICROCONTROLLER'][0] and 0 <= y <= BOARD_DIMS[1]-SIZES['MICROCONTROLLER'][1]:
                    yield (x, y)
        for dy in range(-r+1, r):
            for dx in (-r, r):
                x = cx + dx
                y = cy + dy
                if 0 <= x <= BOARD_DIMS[0]-SIZES['MICROCONTROLLER'][0] and 0 <= y <= BOARD_DIMS[1]-SIZES['MICROCONTROLLER'][1]:
                    yield (x, y)

def find_solution(timeout=1.8):
    """
    Attempt to find a valid placement within timeout seconds.
    Returns placement dict or None.
    """
    t0 = time.perf_counter()

    base = place_edge_components()
    # We'll attempt microcontroller positions prioritized near center
    mc_w, mc_h = SIZES['MICROCONTROLLER']
    xt_w, xt_h = SIZES['CRYSTAL']

    best = None
    best_score = float('inf')
    # Precompute keepout zone depends on USB position (we already placed USB)
    usb = base['USB_CONNECTOR']
    keepout_zone = compute_keepout_zone(usb)

    for (mx, my) in prioritized_positions():
        # stop if timeout
        if time.perf_counter() - t0 > timeout:
            break
        # candidate microcontroller bounding box
        mc = {'x': mx, 'y': my, 'w': mc_w, 'h': mc_h}
        # skip overlap with edge items
        overlap_edge = any(bbox_overlap(mc, base[k]) for k in base.keys())
        if overlap_edge:
            continue

        mc_center = center_of(mc)
        # for each crystal candidate within proximity radius on grid
        min_cx = max(0, int(mc_center[0] - PROXIMITY_RADIUS))
        max_cx = min(BOARD_DIMS[0] - xt_w, int(mc_center[0] + PROXIMITY_RADIUS))
        min_cy = max(0, int(mc_center[1] - PROXIMITY_RADIUS))
        max_cy = min(BOARD_DIMS[1] - xt_h, int(mc_center[1] + PROXIMITY_RADIUS))
        # iterate candidate crystal positions
        for cx in range(min_cx, max_cx+1, GRID_STEP):
            # early break if timeout
            if time.perf_counter() - t0 > timeout:
                break
            for cy in range(min_cy, max_cy+1, GRID_STEP):
                xt = {'x': cx, 'y': cy, 'w': xt_w, 'h': xt_h}
                xt_center = center_of(xt)
                # proximity check
                if distance(mc_center, xt_center) > PROXIMITY_RADIUS:
                    continue
                # boundary checks
                if not in_bounds(xt):
                    continue
                # overlap checks with edge components
                if any(bbox_overlap(xt, base[k]) for k in base.keys()):
                    continue
                # no overlap between mc and xt (shouldn't happen but check)
                if bbox_overlap(xt, mc):
                    continue

                # assemble placement
                placement = {}
                placement.update(base)
                placement['MICROCONTROLLER'] = mc
                placement['CRYSTAL'] = xt

                # global balance check (CoM)
                centers = [center_of(c) for c in placement.values()]
                com_x = sum(c[0] for c in centers)/len(centers)
                com_y = sum(c[1] for c in centers)/len(centers)
                com_dist = distance((com_x, com_y), (BOARD_DIMS[0]/2.0, BOARD_DIMS[1]/2.0))
                if com_dist > CENTER_OF_MASS_RADIUS:
                    continue

                # keepout check: crystal-microcontroller line must NOT intersect keepout zone
                if line_intersects_rect(center_of(placement['CRYSTAL']), center_of(placement['MICROCONTROLLER']), keepout_zone):
                    continue

                # final overlap checks across all components
                comps = list(placement.items())
                collision = False
                for i in range(len(comps)):
                    for j in range(i+1, len(comps)):
                        if bbox_overlap(comps[i][1], comps[j][1]):
                            collision = True
                            break
                    if collision:
                        break
                if collision:
                    continue

                # compute score and keep best (lower is better)
                total_score, bbox_area, centrality = compute_score(placement)
                if total_score < best_score:
                    best_score = total_score
                    best = (placement.copy(), total_score, bbox_area, centrality)
                    # since our prioritized search is center-first, we can accept near optimal quickly
    if best:
        return best[0], best[1], best[2], best[3]
    return None, None, None, None

def plot_and_save(placement, out_png="placement_snapshot_algo.png"):
    fig, ax = plt.subplots(figsize=(8,8))
    ax.set_xlim(0, BOARD_DIMS[0])
    ax.set_ylim(0, BOARD_DIMS[1])
    ax.set_xticks(range(0, BOARD_DIMS[0]+1, 5))
    ax.set_yticks(range(0, BOARD_DIMS[1]+1, 5))
    ax.grid(True, linestyle='--', color='gray', alpha=0.3)
    ax.set_aspect('equal', adjustable='box')
    ax.invert_yaxis()
    ax.set_title("PCB Component Placement Solution (Algorithmic)")

    color_map = {
        'USB_CONNECTOR': '#e74c3c',
        'MICROCONTROLLER': '#3498db',
        'CRYSTAL': '#f39c12',
        'MIKROBUS_CONNECTOR_1': '#9b59b6',
        'MIKROBUS_CONNECTOR_2': '#8e44ad'
    }
    labels = {
        'USB_CONNECTOR': 'USB',
        'MICROCONTROLLER': 'μC',
        'CRYSTAL': 'XTAL',
        'MIKROBUS_CONNECTOR_1': 'MB1',
        'MIKROBUS_CONNECTOR_2': 'MB2'
    }

    for name, comp in placement.items():
        rect = patches.Rectangle((comp['x'], comp['y']), comp['w'], comp['h'],
                                 linewidth=1.5, edgecolor='black', facecolor=color_map[name])
        ax.add_patch(rect)
        ax.text(comp['x'] + comp['w']/2.0, comp['y'] + comp['h']/2.0, labels[name],
                color='white', ha='center', va='center', fontweight='bold')

    # proximity circle around microcontroller
    uc_center = center_of(placement['MICROCONTROLLER'])
    circle = patches.Circle(uc_center, PROXIMITY_RADIUS, fill=True, color='#f39c12', alpha=0.1, linestyle='--')
    ax.add_patch(circle)

    # keepout zone from USB
    zone = compute_keepout_zone(placement['USB_CONNECTOR'])
    keepout = patches.Rectangle((zone['x'], zone['y']), zone['w'], zone['h'], fill=True, color='#e74c3c', alpha=0.15, linestyle='--')
    ax.add_patch(keepout)

    # draw line between crystal and microcontroller
    xt_center = center_of(placement['CRYSTAL'])
    ax.plot([xt_center[0], uc_center[0]], [xt_center[1], uc_center[1]], 'k--', linewidth=2)

    plt.savefig(out_png, bbox_inches='tight', dpi=200)
    plt.close()
    return out_png

def main():
    t0 = time.perf_counter()

    placement, score_val, bbox_area, centrality = find_solution(timeout=1.8)
    if placement is None:
        print("No valid placement found within time limit.")
        return

    # format placement keys to match checker exact names
    # we already used same names
    # finalize and validate with the included validator logic
    valid, results = validate_full(placement)
    t1 = time.perf_counter()
    elapsed = t1 - t0

    # print validator-style summary
    print("--- DEMO: Algorithmic Placement ---")
    print("--- Running Detailed Hard Constraint Validation ---")
    for rule, (ok, msg) in results.items():
        status = "✅ PASSED" if ok else "❌ FAILED"
        print(f"{rule:<22}: {status} {msg}")

    print("\n--- Performance Report for Validation and Placement ---")
    print(f"Placement search + validation finished in: {elapsed:.6f} seconds")
    if elapsed <= VALIDATION_TIME_LIMIT:
        print("✅ PERFORMANCE PASSED (under 2s)")
    else:
        print("❌ PERFORMANCE FAILED (too slow)")

    # compute final score
    total_score, bbox_area, centrality = compute_score(placement)
    print("\n--- Calculated Score ---")
    print(f"Compactness (Bounding Box Area): {bbox_area:.2f}")
    print(f"Centrality (uC distance to center): {centrality:.2f}")
    print(f"Total Combined Score: {total_score:.2f}")

    # save outputs
    out_json = "my_algorithmic_placement.json"
    with open(out_json, "w") as fh:
        json.dump(placement, fh, indent=2)
    out_png = plot_and_save(placement, out_png="placement_snapshot_algo.png")
    out_txt = "self_score_algo.txt"
    with open(out_txt, "w") as fh:
        fh.write("Validation Results:\n")
        for rule, (ok, msg) in results.items():
            fh.write(f"{rule}: {'PASS' if ok else 'FAIL'} {msg}\n")
        fh.write(f"\nPlacement search+validation time: {elapsed:.6f} s\n")
        fh.write(f"Total Score: {total_score:.2f}\n")
        fh.write(f"Compactness (area): {bbox_area:.2f}\n")
        fh.write(f"Centrality: {centrality:.2f}\n")

    print(f"\nSaved placement JSON: {out_json}")
    print(f"Saved snapshot PNG: {out_png}")
    print(f"Saved self-score TXT: {out_txt}")

if __name__ == "__main__":
    main()
