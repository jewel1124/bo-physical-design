import csv
from pathlib import Path

import pandas as pd
from skopt import gp_minimize
from skopt.space import Integer, Real

from run_experiments import run_one



OUT_CSV = Path("dataset/APU_bo_dataset_3.csv")
OUT_CSV.parent.mkdir(exist_ok=True)


N_CALLS = 10
N_INITIAL_POINTS = 3


SPACE = [
    Integer(35, 50, name="FP_CORE_UTIL"),
    Real(0.8, 1.2, name="FP_ASPECT_RATIO"),
    Real(0.50, 0.70, name="PL_TARGET_DENSITY"),
]

rows = []
evaluated = {}




def save_bo_csv(rows):
    if not rows:
        return

    fieldnames = [
        "bo_iter",
        "tag",
        "util",
        "aspect_ratio",
        "density",
        "status",
        "runtime_sec",
        "die_area",
        "total_power",
        "wirelength", 
        "wns",
        "worst_slack",
        "drc",

        "cost",
    ]

    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)





def objective(params):
    util, aspect_ratio, density = params

    util = int(util)
    aspect_ratio = round(float(aspect_ratio), 2)
    density = round(float(density), 2)

    print("=" * 90)
    print(f"[BO] Suggested: util={util}, ar={aspect_ratio}, density={density}")
    print("=" * 90)


    key = (util, aspect_ratio, density)

    # Tránh chạy lại cùng một cấu hình
    if key in evaluated:
        print(f"[BO] Duplicate config. Reuse cost = {evaluated[key]}")
        return evaluated[key]

    row = run_one(util, aspect_ratio, density)

    row["bo_iter"] = len(rows) + 1
    rows.append(row)

    save_bo_csv(rows)

    cost = row.get("cost")

    if cost is None or cost > 1e6:
        cost = 2

    evaluated[key] = cost

    print(f"[BO] Cost = {cost}")
    return cost



def main():
    print("=" * 90)
    print(" BAYESIAN OPTIMIZATION FOR APU")
    print("=" * 90)
    print(f"N_CALLS = {N_CALLS}")
    print(f"N_INITIAL_POINTS = {N_INITIAL_POINTS}")
    print(f"Output CSV = {OUT_CSV}")
    print("=" * 90)

    result = gp_minimize(
        func=objective,
        dimensions=SPACE,
        n_calls=N_CALLS,
        n_initial_points=N_INITIAL_POINTS,
        acq_func="LCB",
        acq_optimizer = "sampling",
        kappa = 2.5,
        random_state=42,
        noise = 0.01,
        
    )

    print("\n" + "=" * 90)
    print(" BO FINISHED")
    print("=" * 90)
    print("Best parameters:")
    print(f"  FP_CORE_UTIL      = {int(result.x[0])}")
    print(f"  FP_ASPECT_RATIO   = {round(float(result.x[1]), 2)}")
    print(f"  PL_TARGET_DENSITY = {round(float(result.x[2]), 2)}")
    print(f"Best cost = {result.fun}")
    print("=" * 90)

    if OUT_CSV.exists():
        df = pd.read_csv(OUT_CSV)

        valid = df[
            (df["status"] == "ok") &
            (df["drc"] == 0) &
            (df["wns"] >= 0)
        ].copy()

        if len(valid) > 0:
            print("\n===== TOP 10 BO CONFIGS =====")
            print(valid.sort_values("cost").head(10)[[
                "bo_iter",
                "tag",
                "util",
                "aspect_ratio",
                "density",
                "die_area",
                "wns",
                "worst_slack",
                "drc",
                "cost",
            ]])
        else:
            print("[WARN] No valid BO run found.")

    print(f"\nSaved BO dataset to: {OUT_CSV}")


if __name__ == "__main__":
    main()