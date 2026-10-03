import polars as pl
import numpy as np

def map_protocol(protocol_col: pl.Expr) -> pl.Expr:
    """Maps IANA protocol numbers to contract vocabulary."""
    return (
        pl.when(protocol_col == 6).then(pl.lit("TCP"))
        .when(protocol_col == 17).then(pl.lit("UDP"))
        .when(protocol_col == 0).then(pl.lit("HOPOPT"))
        .otherwise(pl.lit("UNKNOWN"))
    )

def build_flow_records(lf: pl.LazyFrame) -> pl.LazyFrame:
    """
    Transforms the raw CIC-DDoS2019 dataset into canonical FlowRecords.
    """
    # Standardize column names
    rename_map = {c: c.strip() for c in lf.columns}
    lf = lf.rename(rename_map)
    
    # Parse timestamp - handles multiple formats found in CIC-DDoS2019
    parsed_time = pl.coalesce([
        pl.col("Timestamp").str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S.%f", strict=False),
        pl.col("Timestamp").str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S", strict=False),
        pl.col("Timestamp").str.strptime(pl.Datetime, "%d/%m/%Y %H:%M:%S", strict=False),
        pl.col("Timestamp").str.strptime(pl.Datetime, "%d/%m/%Y %H:%M", strict=False)
    ])
    
    lf = lf.with_columns(
        parsed_time.alias("event_ts")
    )
    
    # Drop unparseable
    lf = lf.filter(pl.col("event_ts").is_not_null())
    
    # Extract needed contract fields
    lf = lf.select([
        pl.col("Flow ID").alias("flow_id"),
        pl.col("event_ts"),
        (pl.col("Flow Duration") / 1000.0).alias("duration_ms"),
        (pl.col("Total Length of Fwd Packets") + pl.col("Total Length of Bwd Packets")).alias("byte_count"),
        (pl.col("Total Fwd Packets") + pl.col("Total Backward Packets")).alias("packet_count"),
        map_protocol(pl.col("Protocol")).alias("protocol"),
        pl.col("Label").alias("label_type"),
        (pl.col("Label") != "BENIGN").cast(pl.Int32).alias("label_binary"),
    ])
    
    # Sort by time
    lf = lf.sort("event_ts")
    return lf

def build_binned_stream(lf: pl.LazyFrame, bin_width_s: float = 1.0) -> pl.LazyFrame:
    """
    Aggregates flow records into time bins of width `bin_width_s`.
    Computes `n_flows`, `sum_bytes`, and `sum_packets` per bin.
    Also computes the channels: `len`, `rate_pkts`, `rate_flows`.
    """
    # Compute epoch seconds and bin index
    lf = lf.with_columns(
        (pl.col("event_ts").dt.epoch("ms") / 1000.0).alias("epoch_s")
    )
    lf = lf.with_columns(
        (pl.col("epoch_s") // bin_width_s).cast(pl.Int64).alias("bin_id")
    )
    
    # Group by bin_id
    binned = lf.group_by("bin_id").agg([
        pl.len().alias("n_flows"),
        pl.col("byte_count").sum().alias("sum_bytes"),
        pl.col("packet_count").sum().alias("sum_packets"),
        pl.col("label_binary").sum().alias("attack_flows"),
        pl.col("label_type").mode().first().alias("majority_label_type")
    ]).sort("bin_id")
    
    # Compute channels and handle empty bin zeroes
    binned = binned.with_columns([
        (pl.col("sum_bytes") / pl.col("sum_packets")).fill_nan(0.0).alias("len"),
        (pl.col("sum_packets").log1p()).alias("rate_pkts"),
        (pl.col("n_flows").log1p()).alias("rate_flows")
    ])
    
    return binned

def build_windows(binned_df: pl.DataFrame, T: int = 256, stride: int = 8, tau: float = 0.5, tail_bins: int = 16, min_attack_flows: int = 5) -> pl.DataFrame:
    """
    Extracts windows of size `T` from the binned stream using a sliding window.
    Empty bins (missing bin_ids) are explicitly filled with zeros before windowing.
    """
    if len(binned_df) == 0:
        return pl.DataFrame()
        
    min_bin = binned_df["bin_id"].min()
    max_bin = binned_df["bin_id"].max()
    
    # Create a continuous range of bin_ids
    full_range = pl.DataFrame({"bin_id": np.arange(min_bin, max_bin + 1, dtype=np.int64)})
    
    # Join and fill nulls
    dense_binned = full_range.join(binned_df, on="bin_id", how="left")
    dense_binned = dense_binned.with_columns([
        pl.col("n_flows").fill_null(0),
        pl.col("sum_bytes").fill_null(0.0),
        pl.col("sum_packets").fill_null(0),
        pl.col("attack_flows").fill_null(0),
        pl.col("majority_label_type").fill_null("BENIGN"),
        pl.col("len").fill_null(0.0),
        pl.col("rate_pkts").fill_null(0.0),
        pl.col("rate_flows").fill_null(0.0)
    ])
    
    # We want to extract rolling windows of size T, stride `stride`.
    # To do this efficiently in polars:
    # We can use `rolling` or manually create window indices.
    # Given we need a 3D tensor eventually, let's extract the start indices.
    n_bins = len(dense_binned)
    start_indices = np.arange(0, n_bins - T + 1, stride)
    
    if len(start_indices) == 0:
        return pl.DataFrame()
        
    windows = []
    # For very large datasets, a custom numpy stride trick is much faster,
    # but for initial implementation and validation, let's just collect them.
    # Actually, we should return the dense sequence and let the caller stride it,
    # or return a structured dataframe with window indices.
    # Let's use the numpy sliding_window_view for speed if needed, 
    # but here we can just return the dense_binned and let the modeling step stride it, 
    # OR construct the window labels here.
    
    # Let's construct the window labels:
    # A window ending at index `i + T` (exclusive) has a tail of `tail_bins`.
    attack_flows_arr = dense_binned["attack_flows"].to_numpy()
    n_flows_arr = dense_binned["n_flows"].to_numpy()
    label_types_arr = dense_binned["majority_label_type"].to_numpy()
    
    labels = []
    attack_fractions = []
    window_attack_types = []
    
    for start_idx in start_indices:
        end_idx = start_idx + T
        tail_start = end_idx - tail_bins
        
        tail_attack = attack_flows_arr[tail_start:end_idx].sum()
        tail_total = n_flows_arr[tail_start:end_idx].sum()
        
        attack_frac = tail_attack / tail_total if tail_total > 0 else 0.0
        
        is_attack = (attack_frac >= tau) and (tail_attack >= min_attack_flows)
        
        # Determine majority attack type in the window (excluding BENIGN)
        window_types = label_types_arr[start_idx:end_idx]
        attack_types = window_types[window_types != "BENIGN"]
        if len(attack_types) > 0:
            vals, counts = np.unique(attack_types, return_counts=True)
            maj_type = vals[np.argmax(counts)]
        else:
            maj_type = "BENIGN"
            
        labels.append(int(is_attack))
        attack_fractions.append(attack_frac)
        window_attack_types.append(maj_type)
        
    windows_df = pl.DataFrame({
        "window_start_bin": dense_binned["bin_id"].to_numpy()[start_indices],
        "label": labels,
        "attack_fraction": attack_fractions,
        "majority_attack_type": window_attack_types
    })
    
    return windows_df, dense_binned
