import numpy as np
from sklearn.metrics import f1_score, precision_score, recall_score, average_precision_score, matthews_corrcoef, confusion_matrix

def compute_window_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_prob: np.ndarray = None):
    """
    Compute core metrics for window-level classification.
    """
    metrics = {}
    
    # Macro metrics
    metrics['macro_f1'] = f1_score(y_true, y_pred, average='macro', zero_division=0)
    
    # Class-specific (Attack=1, Benign=0)
    metrics['attack_f1'] = f1_score(y_true, y_pred, pos_label=1, zero_division=0)
    metrics['attack_precision'] = precision_score(y_true, y_pred, pos_label=1, zero_division=0)
    metrics['attack_recall'] = recall_score(y_true, y_pred, pos_label=1, zero_division=0)
    
    metrics['benign_f1'] = f1_score(y_true, y_pred, pos_label=0, zero_division=0)
    metrics['benign_precision'] = precision_score(y_true, y_pred, pos_label=0, zero_division=0)
    metrics['benign_recall'] = recall_score(y_true, y_pred, pos_label=0, zero_division=0)
    
    # MCC
    metrics['mcc'] = matthews_corrcoef(y_true, y_pred)
    
    # PR-AUC
    if y_prob is not None:
        metrics['pr_auc_attack'] = average_precision_score(y_true, y_prob, pos_label=1)
        metrics['pr_auc_benign'] = average_precision_score(1 - y_true, 1 - y_prob, pos_label=1)
    
    # Confusion matrix elements
    if len(np.unique(y_true)) > 1:
        tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
        metrics['tn'] = int(tn)
        metrics['fp'] = int(fp)
        metrics['fn'] = int(fn)
        metrics['tp'] = int(tp)
    
    return metrics

def block_bootstrap_ci(y_true: np.ndarray, y_pred: np.ndarray, metric_fn, n_bootstrap=1000, block_size=10):
    """
    Compute 95% CI using block bootstrapping to account for temporal dependence.
    """
    n_samples = len(y_true)
    n_blocks = n_samples // block_size
    
    if n_blocks == 0:
        return 0.0, 0.0 # Not enough data
        
    scores = []
    
    for _ in range(n_bootstrap):
        # Sample block indices with replacement
        block_indices = np.random.choice(n_blocks, size=n_blocks, replace=True)
        
        # Unroll block indices to sample indices
        sample_indices = []
        for bi in block_indices:
            start_idx = bi * block_size
            sample_indices.extend(range(start_idx, start_idx + block_size))
            
        y_t_boot = y_true[sample_indices]
        y_p_boot = y_pred[sample_indices]
        
        if len(np.unique(y_t_boot)) > 1:
            scores.append(metric_fn(y_t_boot, y_p_boot))
            
    if not scores:
        return 0.0, 0.0
        
    lower = np.percentile(scores, 2.5)
    upper = np.percentile(scores, 97.5)
    return float(lower), float(upper)
