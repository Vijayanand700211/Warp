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
        # To be safe, we just take proportions of the raw length, then drop the gap boundaries
        n_train_raw = int(0.70 * n_windows)
        n_val_raw = int(0.15 * n_windows)
        
        train_end = n_train_raw
        val_start = train_end + gap_windows
        val_end = val_start + n_val_raw
        test_start = val_end + gap_windows
        
        # If test_start pushes beyond bounds due to rounding, adjust
        if test_start >= n_windows:
            # Revert to all train if we can't fit
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

