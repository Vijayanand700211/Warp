import numpy as np
import polars as pl
import logging

def split_pa_in_session(windows_df: pl.DataFrame, T: int = 256) -> pl.DataFrame:
    """
    Implements P-A split: blocked temporal, in-session.
    Cuts the timeline into contiguous segments (maximal runs of the same label-type).
    Within each segment:
    - 70% train
    - 15% val
    - 15% test
    With a gap of `T` bins between adjacent blocks.
    Segments too short to split go wholly to train.
    """
    if len(windows_df) == 0:
        return windows_df.with_columns(pl.lit("train").alias("split"))

    # To find contiguous segments, we look at where the majority_attack_type changes
    # But wait, windows overlap! The label of the window is based on the tail.
    # The specification says: "contiguous segments (maximal runs of the same label-type; benign gaps are their own segments)".
    # This refers to the flow/bin level, not the overlapping windows level.
    # However, since each window has a `majority_attack_type` and a start bin, 
    # we can approximate this by grouping contiguous runs of windows with the same `majority_attack_type`.
    
    # Identify segment boundaries
    attack_types = windows_df["majority_attack_type"].to_numpy()
    start_bins = windows_df["window_start_bin"].to_numpy()
    
    # A new segment starts if attack_type changes OR if there is a massive time gap in start_bins
    # (e.g. across different files or real time gaps)
    # A gap larger than T means the windows are completely disjoint.
    type_changes = np.concatenate([[True], attack_types[1:] != attack_types[:-1]])
    time_gaps = np.concatenate([[True], np.diff(start_bins) > T])
    segment_starts = type_changes | time_gaps
    
    segment_ids = np.cumsum(segment_starts)
    
    # Create a column for split
    splits = np.array(["train"] * len(windows_df), dtype=object)
    
    for seg_id in np.unique(segment_ids):
        mask = (segment_ids == seg_id)
        indices = np.where(mask)[0]
        n_windows = len(indices)
        
        # A split requires 70/15/15. We also need a gap of T bins between blocks.
        # Since stride is `S` (e.g. 8), a gap of T bins means skipping T/S windows.
        # Let's say T=256, S=8, gap_windows = 32.
        # If n_windows is too small to even hold the gaps, the whole segment goes to train.
        
        # We need roughly gap_windows = ceil(T / median_stride)
        if n_windows > 1:
            stride = np.median(np.diff(start_bins[indices]))
            if stride > 0:
                gap_windows = int(np.ceil(T / stride))
            else:
                gap_windows = 0
        else:
            gap_windows = 0
            
        # Minimum size to split: need at least 1 window for train, val, test, plus 2 gaps
        min_required = 1 + gap_windows + 1 + gap_windows + 1
        
        if n_windows < min_required:
            # Segment too short, stays wholly in train
            continue
            
        # Split 70 / 15 / 15 of the active windows (excluding the gaps from the percentages)
        usable_windows = n_windows - 2 * gap_windows
        if usable_windows < 3:
            continue
            
        n_train_raw = int(0.70 * usable_windows)
        n_val_raw = int(0.15 * usable_windows)
        
        # Ensure at least 1 window per split if possible
        if n_train_raw == 0: n_train_raw = 1
        if n_val_raw == 0: n_val_raw = 1
        
        train_end = n_train_raw
        val_start = train_end + gap_windows
        val_end = val_start + n_val_raw
        test_start = val_end + gap_windows
        
        # If test_start pushes beyond bounds due to rounding, adjust test_start
        # If it still overflows, just put all in train
        if test_start >= n_windows:
            if val_end + gap_windows < n_windows:
                test_start = val_end + gap_windows
            else:
                continue
            
        # Assign splits
        # The default is "train" which is already set
        # We need to mark the gaps as "drop"
        splits[indices[train_end:val_start]] = "drop"
        splits[indices[val_start:val_end]] = "val"
        splits[indices[val_end:test_start]] = "drop"
        splits[indices[test_start:]] = "test"
        
    out_df = windows_df.with_columns(
        pl.Series("split", splits)
    )
    
    # Filter out dropped gap windows
    return out_df.filter(pl.col("split") != "drop")


def split_pb_cross_session(windows_df: pl.DataFrame, T: int = 256) -> pl.DataFrame:
    """
    Implements P-B split: cross-session (generalization).
    Train/val from earlier capture day(s), test from the later day.
    Val = last 15% blocks of the train day with gaps.
    Mark N/A if timestamps expose only one day.
    """
    if len(windows_df) == 0:
        return windows_df.with_columns(pl.lit("train").alias("split"))

    # Convert start bins to days
    # Since bin_width_s = 1.0 (default), bin_id is epoch_s.
    # epoch_s // 86400 gives the day.
    start_bins = windows_df["window_start_bin"].to_numpy()
    days = start_bins // 86400
    unique_days = np.unique(days)
    
    if len(unique_days) <= 1:
        # Cannot do cross-session split on a single day.
        # Fallback to P-A or all train. We will just return all train with a warning.
        logging.warning("P-B split requested but only one day of data found. Falling back to all train.")
        return windows_df.with_columns(pl.lit("train").alias("split"))
        
    last_day = unique_days[-1]
    
    # Test is the last day
    test_mask = (days == last_day)
    train_val_mask = ~test_mask
    
    train_val_indices = np.where(train_val_mask)[0]
    n_train_val = len(train_val_indices)
    
    splits = np.array(["train"] * len(windows_df), dtype=object)
    splits[test_mask] = "test"
    
    # Val is the last 15% of the train_val day(s) with gaps
    if n_train_val > 1:
        stride = np.median(np.diff(start_bins[train_val_indices]))
        gap_windows = int(np.ceil(T / stride)) if stride > 0 else 0
    else:
        gap_windows = 0
        
    # We want 15% of usable windows for val
    usable_windows = n_train_val - gap_windows
    
    if usable_windows >= 2:
        n_val_raw = int(0.15 * usable_windows)
        if n_val_raw == 0: n_val_raw = 1
        
        val_end = n_train_val
        val_start = val_end - n_val_raw
        train_end = val_start - gap_windows
        
        if train_end > 0:
            splits[train_val_indices[train_end:val_start]] = "drop"
            splits[train_val_indices[val_start:val_end]] = "val"
        
    out_df = windows_df.with_columns(
        pl.Series("split", splits)
    )
    
    return out_df.filter(pl.col("split") != "drop")

