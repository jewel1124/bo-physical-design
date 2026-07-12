import csv
import json
import re
import shutil
import subprocess
import time
from pathlib import Path



WORK_DIR = Path("/home/tuan/librelane_work/librelane/test")

DESIGN_NAME = "APU"


CONFIG_PATH = WORK_DIR / "designs" / DESIGN_NAME / "config.json"

DOCKER_IMAGE = "ghcr.io/librelane/librelane:2.4.13"

LOG_DIR = Path("logs")
DATASET_DIR = Path("dataset")

LOG_DIR.mkdir(exist_ok=True)
DATASET_DIR.mkdir(exist_ok=True)

OUT_CSV = DATASET_DIR / f"{DESIGN_NAME}_dataset_3.csv"

TIMEOUT_SECONDS = 30 * 60



def backup_config():
    """
    Backup config gốc một lần duy nhất.
    """
    backup_path = CONFIG_PATH.with_suffix(".json.bak")

    if not backup_path.exists():
        shutil.copy(CONFIG_PATH, backup_path)
        print(f"[INFO] Backup config created: {backup_path}")


def update_config_json(util, aspect_ratio, density):
    """
    Sửa 3 tham số tuning trong block pdk::sky130*.
    """
    backup_config()

    with CONFIG_PATH.open("r") as f:
        config = json.load(f)

    if "pdk::sky130*" not in config:
        config["pdk::sky130*"] = {}

    config["pdk::sky130*"]["FP_CORE_UTIL"] = util
    config["pdk::sky130*"]["FP_ASPECT_RATIO"] = aspect_ratio
    config["pdk::sky130*"]["PL_TARGET_DENSITY"] = density

    with CONFIG_PATH.open("w") as f:
        json.dump(config, f, indent=4)

    print(
        f"[CONFIG] FP_CORE_UTIL={util}, "
        f"FP_ASPECT_RATIO={aspect_ratio}, "
        f"PL_TARGET_DENSITY={density}"
    )


def make_tag(util, aspect_ratio, density):
    """
    Tạo tên run tag riêng cho từng cấu hình.
    """
    return f"{DESIGN_NAME}_u{util}_ar{aspect_ratio}_den{density}".replace(".", "p")




def make_command(tag):
    return [
        "docker", "run", "--rm",
        "-v", f"{WORK_DIR}:/work",
        "-v", "/home/tuan/.ciel:/home/librelane/.ciel",
        "-v", "/home/tuan/.ciel:/root/.ciel",
        "-w", "/work",
        DOCKER_IMAGE,
        "librelane",
        f"designs/{DESIGN_NAME}/config.json",
        "--run-tag", tag,
    ]


def run_librelane(tag):
    cmd = make_command(tag)

    print("[RUN]", " ".join(cmd))

    start = time.time()

    try:
        result = subprocess.run(
            cmd,
            cwd=WORK_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )

        runtime = time.time() - start
        status = "ok" if result.returncode == 0 else "failed"

        return result.returncode, result.stdout, runtime, status

    except subprocess.TimeoutExpired as e:
        runtime = time.time() - start
        log_text = e.stdout or ""
        return -1, log_text, runtime, "timeout"


def find_metrics_csv(tag):
    """
    Chỉ tìm metrics.csv đúng trong run folder của tag hiện tại.
    Không lấy file mới nhất của run khác.
    """
    run_dir = WORK_DIR / "designs" / DESIGN_NAME / "runs" / tag
    metrics_path = run_dir / "final" / "metrics.csv"

    if metrics_path.exists():
        return metrics_path

    return None


def safe_float(value):
    if value is None:
        return None

    if value == "":
        return None

    try:
        return float(value)
    except Exception:
        return None


def safe_int(value):
    v = safe_float(value)
    if v is None:
        return None
    return int(v)


def parse_metrics_csv(metrics_path):
   
    if metrics_path is None or not metrics_path.exists():
        return {}

    try:
        metric_dict = {}

        with metrics_path.open("r") as f:
            reader = csv.DictReader(f)

            for row in reader:
                name = row.get("Metric")
                value = row.get("Value")

                if name is not None:
                    metric_dict[name] = value

        def get_float(name):
            return safe_float(metric_dict.get(name))

        def get_int(name):
            return safe_int(metric_dict.get(name))

        return {
            "die_area": get_float("design__die__area"),
            "core_area": get_float("design__core__area"),
            "cell_area": get_float("design__instance__area"),

            "total_power": get_float("power__total"),
            "worst_slack":  get_float("timing__setup__ws"), 
            "wns": get_float("timing__setup__wns"),
            "tns": get_float("timing__setup__tns"),

            "drc": get_int("magic__drc_error__count"),
            "antenna": get_int("antenna__violating__nets"),

            "wirelength": get_float("route__wirelength"),
            "vias": get_int("route__vias"),
        }

    except Exception as e:
        print(f"[WARN] Cannot parse metrics.csv {metrics_path}: {e}")
        return {}





def calc_cost(row, base_area_for_design = 93093.9, base_total_power_for_design = 0.00317520927637815, base_worst_slack = 2.32626013925084, base_wirelength = 93750, clock_period = 17.0):
   
    if row["status"] != "ok":
        return 2

    area =  row.get("die_area")    
    power = row.get("total_power")
    wns = row.get("wns")
    drc = row.get("drc")
    wire_length = row.get("wirelength")
    worst_slack = row.get("worst_slack")
    if area is None or power is None:
        return 2
    
    area_norm = area / base_area_for_design
    power_norm = power / base_total_power_for_design
    wirelength_norm = wire_length / base_wirelength
    if worst_slack is None:
        perf_norm = 2.0   # phạt
    else:
        critical_path = clock_period - worst_slack
        critical_path_base = clock_period - base_worst_slack
        perf_norm = critical_path / critical_path_base  
        critical_path = clock_period - worst_slack if worst_slack is not None else None
        
        perf_norm = critical_path / critical_path_base  # ∈ (0, 1]

    # Timing penalty riêng cho WNS âm
    wns = row.get("wns")
    timing_penalty = 0
    if wns is not None and wns < 0:
        timing_penalty = abs(wns) * 1e4

    cost = 0.2 * area_norm + 0.3 * power_norm + 0.3 * perf_norm + 0.2 * wirelength_norm + timing_penalty

    return cost


def run_one(util, aspect_ratio, density):
    tag = make_tag(util, aspect_ratio, density)

    print("=" * 90)
    print(f"[START] {tag}")
    print("=" * 90)

    update_config_json(util, aspect_ratio, density)

    returncode, log_text, runtime, status = run_librelane(tag)

    if status != "ok":
        log_path = LOG_DIR / f"{tag}.log"
        log_path.write_text(log_text)
    else:
        log_path = ""

    metrics_path = find_metrics_csv(tag)

    if status == "ok":
         metrics_csv = parse_metrics_csv(metrics_path)
    else:
        metrics_csv = {}
  

    row = {
        "tag": tag,
        "design": DESIGN_NAME,
        "util": util,
        "aspect_ratio": aspect_ratio,
        "density": density,
        "returncode": returncode,
        "status": status,
        "runtime_sec": round(runtime, 2),
        "metrics_path": str(metrics_path) if metrics_path else "",
        **metrics_csv,

    }

    row["cost"] = calc_cost(row)

    print("[RESULT]")
    for k, v in row.items():
        print(f"  {k}: {v}")

    return row




def save_csv(rows):
    if not rows:
        return

    fieldnames = [
        "tag",
        "util",
        "aspect_ratio",
        "density",
        "status",
        "runtime_sec",
        "die_area",
        "total_power",
        "wirelength",
        "worst_slack",
        "drc",
        "wns",
        "cost",
    ]

    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    if not WORK_DIR.exists():
        raise FileNotFoundError(f"Không tìm thấy WORK_DIR: {WORK_DIR}")

    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy CONFIG_PATH: {CONFIG_PATH}")

    print(f"[INFO] WORK_DIR     = {WORK_DIR}")
    print(f"[INFO] DESIGN_NAME  = {DESIGN_NAME}")
    print(f"[INFO] CONFIG_PATH  = {CONFIG_PATH}")
    print(f"[INFO] OUT_CSV      = {OUT_CSV}")


    utils = [ 35,40,45,50]
    aspect_ratios = [0.8, 1.0, 1.2]
    densities = [0.50, 0.55, 0.60, 0.65, 0.70]   
    rows = []

    total = len(utils) * len(aspect_ratios) * len(densities)
    count = 0

    for util in utils:
        for ar in aspect_ratios:
            for density in densities:
                count += 1
                print("\n" + "#" * 90)
                print(f"[EXPERIMENT] {count}/{total}")
                print("#" * 90)

                row = run_one(util, ar, density)
                rows.append(row)

                save_csv(rows)

    print("=" * 90)
    print(f"[DONE] Dataset saved to: {OUT_CSV}")
    print("=" * 90)


if __name__ == "__main__":
    main()