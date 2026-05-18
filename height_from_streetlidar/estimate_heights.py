import csv
import json

from cases import CASES
from height_estimation import estimate_underpass_height


OUTPUT_CSV_PATH = "underpass_heights.csv"


def write_metrics_csv(rows, output_path):
    with open(output_path, "w", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "identificatie",
                "underpass_z_min",
                "underpass_z_max",
                "underpass_h",
                "underpass_candidate_peaks",
            ],
        )
        writer.writeheader()
        for row in rows:
            output_row = dict(row)
            output_row["underpass_candidate_peaks"] = json.dumps(
                output_row["underpass_candidate_peaks"]
            )
            writer.writerow(output_row)


def main():
    rows = [
        estimate_underpass_height(case["las_path"], case["gpkg_path"], verbose=False)["underpass_metrics"]
        for case in CASES
    ]
    write_metrics_csv(rows, OUTPUT_CSV_PATH)
    print(f"Saved CSV summary to {OUTPUT_CSV_PATH}")


if __name__ == "__main__":
    main()
