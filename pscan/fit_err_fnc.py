import matplotlib.pyplot as plt
import numpy as np
from scipy.special import erf
from scipy.optimize import curve_fit
from scipy.stats import chi2

import logging
logger = logging.getLogger(__name__)

np.random.seed(23)
def logistic(x, L, k, x0):
    return L / (1 + np.exp(-k * (x - x0)))

def err_func(x, sigma, x0, A):
    return A*0.5*(1 + erf((x - x0)/(sigma*np.sqrt(2))))

def fit_s_curve(x, y, curve_type="erf"):
    """
    Fit an S-curve to x, y data and return parameters and uncertainties.

    Returns:
        params : fitted parameters
        params_err : 1-sigma uncertainties
    """
    x = np.array(x)
    y = np.array(y)

    if curve_type == "logistic":
        model = logistic
        x0_guess = np.median(x)
        k_guess = np.gradient(y, x)[len(x)//2]
        p0 = [max(y), k_guess, x0_guess]

    elif curve_type == "erf":
        model = err_func
        p0 = [1.0, np.median(x), 1]
    else:
        raise ValueError("curve_type unknown")

    try:
        params, cov, _, _, ier = curve_fit(model, x, y, p0=p0, full_output=True)
    except Exception as e:
        logger.warning(f"{e}")
        return None

    if ier not in [1, 2, 3, 4]:
        logger.debug(f"Curve fitting: {ier=}")
        return None

    chi2_red = None        # reduced chi-square
    ndof = 1.0* (len(y) - len(params))   # degrees of freedom
    residuals = y - model(x, *params)

    """ To perform a goodness of the fit, the sigma associate to each point is needed
        - Assume that the data is normalize [0:1]. Take the standart deviation for values above 0.9.
    """
    sigma_meas = np.std(y[np.argmin(y > 0.9):-1])
    if sigma_meas == 0:
        chi2_red = np.inf
    else:

        sigma_arr = np.broadcast_to(np.asarray(sigma_meas, dtype=float), y.shape)
        chi2_val = np.sum((residuals / sigma_arr) ** 2)
        chi2_red = chi2_val / ndof

    params_err = np.sqrt(np.diag(cov))

    return [*params, *params_err, chi2_red]

if __name__ == "__main__":
    # Example usage
    x = np.linspace(-5, 5, 100)
    y = logistic(x, 1, 1, 0) + np.random.normal(0, 0.05, x.shape)

    params = fit_s_curve(x, y, curve_type="erf")
    print(params)
    y_fit = err_func(x, *params)
    print("Fitted parameters:", params)

    plt.scatter(x, y, label='Data')
    plt.plot(x, y_fit, color='red', label='Fitted S-curve')
    plt.legend()
    plt.savefig("./s_curve_fit_test.png")
