"""
Deep Dataset Audit Tool for W-MSTSE (Phase P1)
Executes deep checks A3-A11 defined in TASK.md.
"""
import os
import glob
import logging
from pathlib import Path

import polars as pl

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

DATASET_DIRS = [
    Path("dataset/CIC-DDoS2019/01-12"),
    Path("dataset/CIC-DDoS2019/03-11")
]
REPORT_PATH = Path("reports/P1_dataset_audit.md")

def clean_col_name(col):
    return col.strip()

def run_deep_audit():
    csv_files = []
    for d in DATASET_DIRS:
        if d.exists():
            csv_files.extend(list(d.glob("*.csv")))
            
    if not csv_files:
        logging.error("No CSV files found.")
        return

    # Create a unified lazy frame
    lfs = []
    for f in csv_files:
        lf = pl.scan_csv(f, ignore_errors=True, infer_schema_length=10000)
        # normalize column names
        rename_map = {c: clean_col_name(c) for c in lf.columns}
        lf = lf.rename(rename_map)
        
        # We need specific columns to avoid blowing up memory
        # 'Timestamp', 'Label', 'Flow Duration', 'Total Fwd Packets', 'Total Backward Packets'
        # 'Total Length of Fwd Packets', 'Total Length of Bwd Packets', 'Protocol'
        required_cols = [
            "Timestamp", "Label", "Flow Duration", 
            "Total Fwd Packets", "Total Backward Packets",
            "Total Length of Fwd Packets", "Total Length of Bwd Packets", 
            "Protocol", "Flow ID"
        ]
        
        # Check if all required cols exist
        missing = [c for c in required_cols if c not in lf.columns]
        if missing:
            logging.warning(f"File {f.name} missing columns {missing}, skipping for deep audit.")
            continue
            
        lf = lf.select(required_cols)
        # Add a source file column for overlap checks
        lf = lf.with_columns(pl.lit(f.name).alias("source_file"))
        lfs.append(lf)
        
    if not lfs:
        logging.error("No valid CSV files to audit.")
        return

    logging.info("Concatenating files for deep audit...")
    # Concatenate all lazy frames
    df = pl.concat(lfs, how="vertical_relaxed")
    
    # --- A3 Timestamp Parsing ---
    logging.info("Parsing timestamps...")
    # Try two common formats in CIC-DDoS2019
    # Format 1: 2018-12-01 10:51:39.813448
    # Format 2: 01/12/2018 10:51:39
    df = df.with_columns([
        pl.coalesce([
            pl.col("Timestamp").str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S.%f", strict=False),
            pl.col("Timestamp").str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S", strict=False),
            pl.col("Timestamp").str.strptime(pl.Datetime, "%d/%m/%Y %H:%M:%S", strict=False),
            pl.col("Timestamp").str.strptime(pl.Datetime, "%d/%m/%Y %H:%M", strict=False)
        ]).alias("parsed_time")
    ])
    
    logging.info("Executing global aggregations (streaming)...")
    
    # We will build the report incrementally
    report_lines = ["# P1 Dataset Audit Report (Deep Checks)\n"]
    
    # --- A5, A6, A9 Basic Validity and Coverage ---
    # We need to know how many parsed correctly, how many NaNs, negatives, zero packets
    # Streaming collect for basic stats
    stats = df.select([
        pl.len().alias("total_rows"),
        pl.col("parsed_time").is_null().sum().alias("unparsed_timestamps"),
        (pl.col("Flow Duration") < 0).sum().alias("negative_duration"),
        ((pl.col("Total Fwd Packets") + pl.col("Total Backward Packets")) == 0).sum().alias("zero_packet_flows"),
        pl.col("Flow ID").is_null().sum().alias("missing_flow_id")
    ]).collect(streaming=True)
    
    total_rows = stats["total_rows"][0]
    unparsed_ts = stats["unparsed_timestamps"][0]
    
    report_lines.append("## A3. Timestamp Validity")
    report_lines.append(f"- **Total Rows:** {total_rows}")
    report_lines.append(f"- **Unparsable Timestamps:** {unparsed_ts} ({unparsed_ts/total_rows:.4%})")
    if unparsed_ts > 0:
        report_lines.append("> **CAVEAT:** Some timestamps failed to parse. Need to investigate or filter.")
    
    report_lines.append("\n## A5. Value Validity")
    report_lines.append(f"- **Negative Flow Duration:** {stats['negative_duration'][0]}")
    report_lines.append(f"- **Zero Packet Flows:** {stats['zero_packet_flows'][0]}")
    
    report_lines.append("\n## A9. Contract-mapping coverage")
    # All required contract fields exist if they aren't null. The required fields are mapped above.
    report_lines.append("- `byte_count`, `packet_count`, `duration_ms`, `protocol`, `timestamp` can be mapped directly from the CSV columns.")
    report_lines.append(f"- Unmappable rows (due to timestamp parse failures): {unparsed_ts/total_rows:.4%}")
    
    # --- A4, A8 Labels vs Time Sanity ---
    logging.info("Checking labels and time ranges...")
    # Filter to only parsed timestamps for the rest of the time-series analysis
    valid_df = df.filter(pl.col("parsed_time").is_not_null())
    
    # Get distinct labels and their time ranges
    label_stats = valid_df.group_by("Label").agg([
        pl.len().alias("count"),
        pl.col("parsed_time").min().alias("first_seen"),
        pl.col("parsed_time").max().alias("last_seen")
    ]).collect(streaming=True)
    
    report_lines.append("\n## A4 & A8. Labels and Time Sanity")
    for row in label_stats.iter_rows(named=True):
        report_lines.append(f"- **{row['Label']}**: {row['count']} flows. Seen from {row['first_seen']} to {row['last_seen']}")
        
    # --- A10, A11 Window Feasibility & Imbalance ---
    # Window settings: Δ = 1.0s, T = 256. We'll group by 256-second blocks.
    logging.info("Checking Window Feasibility...")
    
    # Create an epoch column in seconds
    window_df = valid_df.with_columns([
        (pl.col("parsed_time").dt.epoch("s")).alias("epoch_s"),
        (pl.col("Label") != "BENIGN").cast(pl.Int32).alias("is_attack")
    ])
    
    # Group by (epoch_s // 256)
    # The label is determined by the trailing 16 bins (seconds 240-255 of the block)
    # tau >= 0.5 and min_attack_flows >= 5
    window_stats = window_df.with_columns([
        (pl.col("epoch_s") // 256).alias("window_id"),
        (pl.col("epoch_s") % 256 >= 240).alias("in_tail")
    ]).group_by("window_id").agg([
        pl.len().alias("window_total_flows"),
        pl.col("in_tail").sum().alias("tail_total_flows"),
        (pl.col("is_attack") & pl.col("in_tail")).sum().alias("tail_attack_flows")
    ]).collect(streaming=True)
    
    window_stats = window_stats.with_columns([
        (pl.col("tail_attack_flows") / pl.col("tail_total_flows")).fill_nan(0.0).alias("tail_attack_fraction")
    ]).with_columns([
        ((pl.col("tail_attack_fraction") >= 0.5) & (pl.col("tail_attack_flows") >= 5)).alias("is_attack_window")
    ])
    
    total_windows = len(window_stats)
    attack_windows = window_stats.filter(pl.col("is_attack_window")).height
    benign_windows = total_windows - attack_windows
    
    report_lines.append("\n## A10 & A11. Window Feasibility (T=256s)")
    report_lines.append(f"- **Total Windows (256s blocks):** {total_windows}")
    report_lines.append(f"- **Benign Windows (tail attack frac < 0.5 or flows < 5):** {benign_windows}")
    report_lines.append(f"- **Attack Windows (tail attack frac >= 0.5 and flows >= 5):** {attack_windows}")
    
    report_lines.append(f"\n- **Window Imbalance Ratio (Benign:Attack):** {benign_windows}:{attack_windows}")
    
    if benign_windows < 30 or attack_windows < 30:
        report_lines.append("\n> **BLOCKER B3:** Fewer than 30 windows of a class! F1 cannot be reliably estimated.")
        verdict = "BLOCK"
    else:
        verdict = "PASS"
        
    report_lines.append("\n## Final Verdict")
    report_lines.append(f"**Verdict: {verdict}**")
    
    with open(REPORT_PATH, "w") as f:
        f.write("\n".join(report_lines))
        
    logging.info(f"Deep audit report written to {REPORT_PATH}")

if __name__ == "__main__":
    run_deep_audit()
