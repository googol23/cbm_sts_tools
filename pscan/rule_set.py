"""
    All method here defined will be applied to results. If at least on call return False
    the fit resutl will be discarded.

    - The method input parameter is the fit result (always check the current output structure of fit_s_curve)
    2025/10/01: fit_s_curve -> [*params, *params_err, chi2_red]
    - The method should return a bool
    - For logging convenience, call all methods rule_XXXXX

"""

def rule_chi2_max(r) -> bool:
    return r[-1] < 0.05

def rule_positive_median(r) -> bool:
    return r[1] > 0

def rule_positive_sigma(r) -> bool:
    return r[0] > 0

