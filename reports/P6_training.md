# Phase P6: Model Training and Initial Evaluation

## Overview
We executed the end-to-end training loop for the three candidate models defined in `TASK.md` (§8.6) on a subset of the CIC-DDoS2019 dataset (`DrDoS_DNS.csv`). 

### Architectures Evaluated
1. **M-floor**: Custom CNN, trained from scratch.
2. **M-main-1**: MobileNetV2, ImageNet-pretrained (via `timm`).
3. **M-main-2**: ViT-Tiny, ImageNet-pretrained (via `timm`).

## Training Results

| Model       | Test Loss | Test Macro-F1 | Test Precision | Test Recall | Test PR-AUC |
|-------------|-----------|---------------|----------------|-------------|-------------|
| M-floor     | 0.5233    | 0.2143        | 0.2727         | 1.0000      | 0.2481      |
| ViT-Tiny    | 1.1575    | 0.2143        | 0.2727         | 1.0000      | 0.2511      |
| MobileNetV2 | 1.9846    | 0.3125        | 0.1000         | 0.1667      | 0.3106      |

## Analysis and Next Steps

**Observation:** Both M-floor and ViT-Tiny achieved `1.000` Recall but only `0.2727` Precision. 
- A Precision of `0.2727` equates to exactly 6 True Positives out of 22 total predictions. Since the test set size is exactly 22 windows, this indicates the models are **predicting the positive class (Attack) for all 22 windows**. 
- This behavior strongly points to severe class imbalance in the specific training file (`DrDoS_DNS.csv`). If the training split contains few-to-no benign windows, the model learns a constant prior and the classification thresholds remain uncalibrated for distinguishing classes.

**Action Required:**
1. **Threshold Calibration:** Implement validation-based thresholding (as per `TASK.md` §10.4) instead of using a default `0.5` logit threshold.
2. **Comprehensive Dataset Evaluation:** Run the training across a more representative split of the full dataset to ensure enough Benign vs. Attack representation, and implement the true P-A / P-B splits with evaluation intervals.
3. **Formal Evaluation Script:** Create `eval/final_report.py` to calculate block-bootstrap CIs, flow-level metrics, and latency constraints, fully completing the P6 / P7 pipeline.
