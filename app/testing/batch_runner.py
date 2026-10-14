"""
Batch Test Corpus Runner and Statistics Evaluator.

Executes test plots through generate_layout_response(), calculates
architectural invariant metrics, produces summary statistics,
and exports detailed results to CSV.
"""
import os
import sys
import time
import csv
from typing import List, Dict, Any, Optional

from app.models.input_models import GenerateLayoutRequest
from app.services.layout_service import generate_layout_response
from app.testing.corpus import CORPUS_20, get_corpus
from app.layout.constraints import check_no_forbidden_doors
from app.config import DOOR_ADJACENCY_FORBIDDEN


def evaluate_candidate(candidate: Dict[str, Any], plot_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract detailed architectural metrics and verify invariants for a candidate.
    """
    validation = candidate.get("validation", {})
    is_valid = validation.get("valid", False)
    errors = validation.get("errors", [])
    warnings = validation.get("warnings", [])
    
    score = candidate.get("score", {})
    overall_score = score.get("overall", 0.0)
    circulation_score = score.get("circulation", 0.0)
    
    doors = candidate.get("doors", [])
    rooms = candidate.get("rooms", [])
    walls = candidate.get("walls", [])
    corridors = candidate.get("corridors", [])
    measurements = candidate.get("measurements", {})
    entrances = candidate.get("entrances", [])
    
    # 1. Entrance room type
    entrance_room_type = None
    entrance_room_id = None
    if entrances:
        entrance_room_id = entrances[0].get("room_id")
        # Find room
        for r in rooms:
            if r.get("id") == entrance_room_id:
                entrance_room_type = r.get("type")
                break
        if not entrance_room_type and entrance_room_id:
            # check corridor
            for c in corridors:
                if c.get("id") == entrance_room_id:
                    entrance_room_type = "corridor"
                    break
                    
    # 2. Check forbidden doors
    room_type_by_id = {r["id"]: r["type"] for r in rooms}
    for c in corridors:
        room_type_by_id[c["id"]] = "corridor"
        
    forbidden_errs = check_no_forbidden_doors(doors, room_type_by_id)
    has_forbidden_doors = len(forbidden_errs) > 0
    forbidden_door_pairs = [e["message"] for e in forbidden_errs]
                
    # 3. BFS Connectivity
    circulation_connected = "CIRCULATION_DISCONNECTED" not in [
        w.get("code") for w in warnings if isinstance(w, dict)
    ] and "CIRCULATION_DISCONNECTED" not in [
        e.get("code") if isinstance(e, dict) else e for e in errors
    ]
    
    # 4. Habitable room daylight & Toilet ventilation
    habitable_types = {"living", "dining", "bedroom", "study"}
    habitable_daylight_pass = True
    toilet_ventilation_pass = True
    
    for r in rooms:
        rtype = r.get("type", "").lower()
        if rtype in habitable_types:
            area_sqm = r.get("area_sqm", 0.0)
            win_area = r.get("window_area_sqm", 0.0)
            # If window_area_sqm not on room, check has_window
            if not r.get("has_window", False) and area_sqm > 0:
                habitable_daylight_pass = False
        elif rtype == "toilet":
            has_vent = r.get("has_ventilation", False) or r.get("has_window", False) or r.get("mechanical_ventilation", False)
            if not has_vent:
                toilet_ventilation_pass = False

    # 5. Area Conservation Delta: carpet + corridor + wall_footprint vs buildable_area
    total_carpet = sum(r.get("carpet_area_sqm", 0.0) for r in rooms)
    corridor_area = measurements.get("corridor_area_sqm", 0.0)
    wall_footprint = measurements.get("total_wall_footprint_area_sqm", 0.0)
    buildable_area = measurements.get("buildable_area_sqm", 0.0)
    area_delta = abs((total_carpet + corridor_area + wall_footprint) - buildable_area)
    
    # 6. Exterior Perimeter Conservation Delta
    exterior_walls = [w for w in walls if w.get("type") == "exterior"]
    exterior_length = sum(w.get("length", 0.0) for w in exterior_walls)
    perimeter_m = measurements.get("perimeter_m", 0.0)
    perimeter_delta = abs(exterior_length - perimeter_m)
    
    return {
        "valid": is_valid,
        "overall_score": round(overall_score, 4),
        "circulation_score": round(circulation_score, 4),
        "door_count": len(doors),
        "room_count": len(rooms),
        "entrance_room_type": entrance_room_type,
        "entrance_room_id": entrance_room_id,
        "has_forbidden_doors": has_forbidden_doors,
        "forbidden_door_pairs": forbidden_door_pairs,
        "circulation_connected": circulation_connected,
        "habitable_daylight_pass": habitable_daylight_pass,
        "toilet_ventilation_pass": toilet_ventilation_pass,
        "area_conservation_delta_sqm": round(area_delta, 4),
        "perimeter_conservation_delta_m": round(perimeter_delta, 4),
        "error_count": len(errors),
        "errors": [e.get("code") if isinstance(e, dict) else str(e) for e in errors],
    }


def run_batch_corpus(
    corpus: Optional[List[Dict[str, Any]]] = None,
    export_csv_path: Optional[str] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Run all plots in the corpus through generate_layout_response(), collect
    detailed metrics, generate summary statistics, and optionally export to CSV.
    """
    if corpus is None:
        corpus = get_corpus()

    results: List[Dict[str, Any]] = []
    
    if verbose:
        print(f"\n{'='*80}")
        print(f"eArchitect Batch Regression Runner — Executing {len(corpus)} Plots")
        print(f"{'='*80}\n")
        print(f"{'ID':<24} | {'Cat':<10} | {'Valid':<5} | {'Score':<6} | {'Doors':<5} | {'Ent':<8} | {'dA(m²)':<7} | {'dP(m)':<6} | {'Time(s)':<6}")
        print(f"{'-'*24}-+-{'-'*10}-+-{'-'*5}-+-{'-'*6}-+-{'-'*5}-+-{'-'*8}-+-{'-'*7}-+-{'-'*6}-+-{'-'*6}")

    start_total = time.time()
    for plot_case in corpus:
        plot_id = plot_case["id"]
        category = plot_case["category"]
        description = plot_case.get("description", "")
        req_data = plot_case["request"]
        
        t0 = time.time()
        try:
            req = GenerateLayoutRequest(**req_data)
            resp = generate_layout_response(req)
            exec_time_ms = round((time.time() - t0) * 1000, 2)
            
            candidates = resp.get("candidates", [])
            cand_count = len(candidates)
            
            if candidates:
                top_cand = candidates[0]
                eval_metrics = evaluate_candidate(top_cand, plot_case)
            else:
                eval_metrics = {
                    "valid": False,
                    "overall_score": 0.0,
                    "circulation_score": 0.0,
                    "door_count": 0,
                    "room_count": 0,
                    "entrance_room_type": None,
                    "entrance_room_id": None,
                    "has_forbidden_doors": False,
                    "forbidden_door_pairs": [],
                    "circulation_connected": False,
                    "habitable_daylight_pass": False,
                    "toilet_ventilation_pass": False,
                    "area_conservation_delta_sqm": 999.0,
                    "perimeter_conservation_delta_m": 999.0,
                    "error_count": 1,
                    "errors": ["NO_CANDIDATES_GENERATED"],
                }
                
            status = "SUCCESS" if eval_metrics["valid"] else "INVALID"
        except Exception as exc:
            exec_time_ms = round((time.time() - t0) * 1000, 2)
            cand_count = 0
            status = "ERROR"
            eval_metrics = {
                "valid": False,
                "overall_score": 0.0,
                "circulation_score": 0.0,
                "door_count": 0,
                "room_count": 0,
                "entrance_room_type": None,
                "entrance_room_id": None,
                "has_forbidden_doors": False,
                "forbidden_door_pairs": [],
                "circulation_connected": False,
                "habitable_daylight_pass": False,
                "toilet_ventilation_pass": False,
                "area_conservation_delta_sqm": 999.0,
                "perimeter_conservation_delta_m": 999.0,
                "error_count": 1,
                "errors": [f"EXCEPTION: {str(exc)}"],
            }
            
        record = {
            "plot_id": plot_id,
            "category": category,
            "description": description,
            "status": status,
            "execution_time_ms": exec_time_ms,
            "candidate_count": cand_count,
            **eval_metrics,
        }
        results.append(record)
        
        if verbose:
            ent_str = str(record["entrance_room_type"])[:8]
            print(
                f"{plot_id:<24} | "
                f"{category[:10]:<10} | "
                f"{str(record['valid']):<5} | "
                f"{record['overall_score']:<6.3f} | "
                f"{record['door_count']:<5d} | "
                f"{ent_str:<8} | "
                f"{record['area_conservation_delta_sqm']:<7.3f} | "
                f"{record['perimeter_conservation_delta_m']:<6.3f} | "
                f"{exec_time_ms / 1000:<6.2f}"
            )

    total_duration_s = time.time() - start_total
    total_plots = len(results)
    valid_count = sum(1 for r in results if r["valid"])
    pass_rate_pct = round((valid_count / total_plots) * 100, 1) if total_plots > 0 else 0.0
    mean_score = round(sum(r["overall_score"] for r in results) / total_plots, 4) if total_plots > 0 else 0.0
    mean_time_ms = round(sum(r["execution_time_ms"] for r in results) / total_plots, 1) if total_plots > 0 else 0.0
    
    # Invariant compliance
    zero_forbidden_count = sum(1 for r in results if not r["has_forbidden_doors"])
    valid_entrance_count = sum(1 for r in results if r["entrance_room_type"] in {"living", "dining", "corridor", "foyer"})
    connected_count = sum(1 for r in results if r["circulation_connected"])
    area_cons_count = sum(1 for r in results if r["area_conservation_delta_sqm"] <= 0.05)
    perim_cons_count = sum(1 for r in results if r["perimeter_conservation_delta_m"] <= 0.5)
    
    summary = {
        "total_plots": total_plots,
        "valid_plots": valid_count,
        "pass_rate_pct": pass_rate_pct,
        "mean_overall_score": mean_score,
        "mean_execution_time_ms": mean_time_ms,
        "total_duration_s": round(total_duration_s, 2),
        "zero_forbidden_doors_pass_rate": round((zero_forbidden_count / total_plots) * 100, 1),
        "valid_entrance_pass_rate": round((valid_entrance_count / total_plots) * 100, 1),
        "circulation_connected_pass_rate": round((connected_count / total_plots) * 100, 1),
        "area_conservation_pass_rate": round((area_cons_count / total_plots) * 100, 1),
        "perimeter_conservation_pass_rate": round((perim_cons_count / total_plots) * 100, 1),
    }
    
    if verbose:
        print(f"\n{'-'*80}")
        print("SUMMARY STATISTICS:")
        print(f"  Total plots evaluated:        {total_plots}")
        print(f"  Valid layouts generated:      {valid_count} / {total_plots} ({pass_rate_pct}%)")
        print(f"  Mean candidate score:         {mean_score:.4f}")
        print(f"  Mean generation time:         {mean_time_ms:.1f} ms")
        print(f"  Total execution time:         {total_duration_s:.2f} s")
        print("ARCHITECTURAL INVARIANT GATES:")
        print(f"  [Gate 1] Zero forbidden doors:        {summary['zero_forbidden_doors_pass_rate']}%")
        print(f"  [Gate 2] Valid entrance room:         {summary['valid_entrance_pass_rate']}%")
        print(f"  [Gate 3] BFS circulation connected:   {summary['circulation_connected_pass_rate']}%")
        print(f"  [Gate 4] Area conservation (<=0.05m²): {summary['area_conservation_pass_rate']}%")
        print(f"  [Gate 5] Perimeter conservation (<=0.5m): {summary['perimeter_conservation_pass_rate']}%")
        print(f"{'='*80}\n")

    # CSV Export
    if export_csv_path:
        os.makedirs(os.path.dirname(os.path.abspath(export_csv_path)), exist_ok=True)
        csv_fields = [
            "plot_id", "category", "description", "status", "valid",
            "execution_time_ms", "candidate_count", "overall_score", "circulation_score",
            "door_count", "room_count", "entrance_room_type", "entrance_room_id",
            "has_forbidden_doors", "circulation_connected",
            "habitable_daylight_pass", "toilet_ventilation_pass",
            "area_conservation_delta_sqm", "perimeter_conservation_delta_m",
            "error_count", "errors"
        ]
        with open(export_csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
            writer.writeheader()
            for r in results:
                row = dict(r)
                row["errors"] = ";".join(r.get("errors", []))
                writer.writerow(row)
        if verbose:
            print(f"CSV report exported to: {export_csv_path}")

    return {
        "summary": summary,
        "results": results,
    }
