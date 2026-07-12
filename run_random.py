import csv
import random
from pathlib import Path

import pandas as pd

from run_experiments import run_one


N_CALLS = 10

UTIL_RANGE = (35, 50)
AR_RANGE = (0.8, 1.2)
DENSITY_RANGE = (0.50, 0.70)

RANDOM_SEED = 42

OUT_CSV = Path("dataset/APU_random_dataset.csv")
OUT_CSV.parent.mkdir(exist_ok=True)

rows = []
evaluated = {}




def sample_config(rng):

    util = rng.randint(UTIL_RANGE[0], UTIL_RANGE[1])
    aspect_ratio = round(rng.uniform(AR_RANGE[0], AR_RANGE[1]), 2)
    density = round(rng.uniform(DENSITY_RANGE[0], DENSITY_RANGE[1]), 2)
    return util, aspect_ratio, density




def save_random_csv(rows):
    if not rows:
        return

    fieldnames = [
        "rs_iter",
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



def main():
    print("=" * 90)
    print(" RANDOM SEARCH FOR APU")
    print("=" * 90)
    print(f"N_CALLS     = {N_CALLS}")
    print(f"RANDOM_SEED = {RANDOM_SEED}")
    print(f"Output CSV  = {OUT_CSV}")
    print("=" * 90)

    rng = random.Random(RANDOM_SEED)

    for i in range(1, N_CALLS + 1):
        util, aspect_ratio, density = sample_config(rng)
        key = (util, aspect_ratio, density)

        print("=" * 90)
        print(f"[RS] Iter {i}/{N_CALLS} - Sampled: util={util}, ar={aspect_ratio}, density={density}")
        print("=" * 90)

        if key in evaluated:
            print(f"[RS] Duplicate config. Reuse cost = {evaluated[key]}")
            row = evaluated[key]["row"]
            cost = evaluated[key]["cost"]
        else:
            row = run_one(util, aspect_ratio, density)
            cost = row.get("cost")
            if cost is None or cost > 1e6:
                cost = 2
            evaluated[key] = {"row": row, "cost": cost}

        row = dict(row)
        row["rs_iter"] = i
        rows.append(row)

        save_random_csv(rows)

        print(f"[RS] Cost = {cost}")

    print("\n" + "=" * 90)
    print(" RANDOM SEARCH FINISHED")
    print("=" * 90)

    if OUT_CSV.exists():
        df = pd.read_csv(OUT_CSV)

        valid = df[
            (df["status"] == "ok") &
            (df["drc"] == 0) &
            (df["wns"] >= 0)
        ].copy()

        if len(valid) > 0:
            best = valid.sort_values("cost").iloc[0]
            print("\nBest parameters (valid configs only):")
            print(f"  FP_CORE_UTIL      = {int(best['util'])}")
            print(f"  FP_ASPECT_RATIO   = {best['aspect_ratio']}")
            print(f"  PL_TARGET_DENSITY = {best['density']}")
            print(f"  Best cost         = {best['cost']}")

            print("\n===== TOP 10 RANDOM SEARCH CONFIGS =====")
            print(valid.sort_values("cost").head(10)[[
                "rs_iter",
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
            print("[WARN] No valid Random Search run found.")

    print(f"\nSaved Random Search dataset to: {OUT_CSV}")


if __name__ == "__main__":
    main()