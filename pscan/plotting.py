import numpy as np
import matplotlib.pyplot as plt
import mplhep
mplhep.style.use("ATLAS")

import logging
logger = logging.getLogger(__name__)

def plot_histogram(x, x_label, y_label, axs=None):
    if axs is None:
        axs = plt.gca()

    x_range = np.max(x) - np.min(x)
    h_mean = np.histogram(x, bins=20, range=[np.min(x) - 0.3*x_range,np.max(x) + 0.3*x_range])
    mplhep.histplot(h_mean, ax=axs)
    axs.set_xlabel(x_label)
    axs.set_ylabel(y_label)
    axs.grid(True)
    return h_mean

from datetime import datetime
def plot_linear_fit(chn, r):
    plt.figure(figsize=(8, 6))
    x    = [adc for adc,v in r.items() if v is not None and isinstance(adc, int)]
    y    = [v[1] for adc,v in r.items() if v is not None and isinstance(adc, int)]
    yerr = [v[4] for adc,v in r.items() if v is not None and isinstance(adc, int)]

    plt.errorbar(x,y, yerr=yerr, fmt='.', capsize=3)
    plt.xlim(x[0]-1, x[-1]+1)
    plt.xlabel('ADC [LSB]')
    plt.ylabel('Thr')

    if 'linear_fit' in r:
        slope     = r['linear_fit'][2]
        intercept = r['linear_fit'][0]
        p_value   = r['linear_fit'][-1]
        x_fit = np.linspace(1,32)
        y_fit = intercept + x_fit*slope
        plt.plot(x_fit, y_fit, color='tab:red')
        plt.grid(True)

        plt.text(
            0.90, 0.95, f"Slope: {slope:.3f}\nIntercept: {intercept:.3f}\np-value: {p_value:.5f}\n",
            transform=plt.gca().transAxes,   # relative coords (0,0) = bottom-left
            fontsize=8, color="gray", alpha=0.7,
            ha="right", va="top"
        )

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    plt.figtext(
        0.01, 0.01, timestamp,
        ha="left", va="bottom",
        fontsize=8, color="gray"
    )

    plt.savefig(f"images/chn_{chn}_thr_vs_adc.png", dpi=300)
    plt.close()


from src.fit_err_fnc import err_func
def plot_s_curve(chn, adc_list, result, data_frame):
    plt.figure(figsize=(8, 6))

    n_of_adc = len(adc_list)
    for adc_idx, adc in enumerate(adc_list):
        df_channel = data_frame[data_frame["CH_value"] == chn]
        if df_channel.empty:
            return None  # in case of missing channels

        x = df_channel['VP_value'].to_numpy()
        y = df_channel[f"ADC_{adc}"].to_numpy()

        # Build edge for histogram
        dx = x[1]-x[0]
        x_edges = [center - 0.5*dx for center in x]
        x_edges.append(x_edges[-1]+dx)

        mplhep.histplot(y,x_edges, color='tab:blue', edges=False)
        mplhep.label.exp_label(exp="CBM", llabel="", rlabel=f"CHN_{chn} : {adc_list}")
        plt.xlabel("Pulse amplitude [LSB]")
        plt.ylabel(f"Counts")
        plt.grid(True)

        if result[adc] is not None:
            s0, x0, a0, sg_err, x0_err, a0_err, chi2 = result[adc]

            if sg_err / s0 > 0.1:
                logger.warning(f"Warning: Large sigma error for channel {chn}, ADC {adc}: {sg_err/s0:.2f}")

            if x0_err / x0 > 0.1:
                logger.warning(f"Warning: Large x0 error for channel {chn}, ADC {adc}: {x0_err/x0:.2f}")

            plt.plot(x, err_func(x,s0,x0, a0), color='tab:red')

        plt.text(
            0.75*(x[-1]-x[0]), 0.20 + 0.8*adc_idx/n_of_adc, f"Sigma: {s0:.3f}\nMean: {x0:.3f}\nChi2_red: {chi2:.5f}\n",
            # transform=plt.gca().transAxes,   # relative coords (0,0) = bottom-left
            fontsize=8, color="gray", alpha=0.7,
            ha="center", va="top"
        )

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    plt.figtext(
        0.01, 0.01, timestamp,
        ha="left", va="bottom",
        fontsize=8, color="gray"
    )
    plt.savefig(f"images/chn_{chn}_s_curve_fit.png")
    plt.close()

