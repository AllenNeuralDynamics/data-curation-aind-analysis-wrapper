# ---------------------
# Standard Library
# ---------------------


# ---------------------
# Third-Party Libraries
# ---------------------
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Set backend before importing pyplot
import matplotlib.pyplot as plt

# ---------------------
# NWB / Domain-Specific Libraries (only what's used)
# ---------------------
from aind_dynamic_foraging_basic_analysis.plot import plot_session_scroller as pss
from aind_dynamic_foraging_basic_analysis.metrics import snr_kurtosis 

def plot_kurtosis_snr_check(nwb, channel_dict, preprocessing = 'dff-bright_mc-iso-IRLS', fps: float = 20.0, loc=None):
    # fip is channels + preprocessing

    channels = channel_dict.keys()

    if preprocessing == "raw":
        fip = channels
    else:
        fip = [f"{ch}_{preprocessing}" for ch in channels]

    # top: zoomed view (1 event row + len(fip) traces)
    n_zoom = 1 + len(fip)
    # bottom: full-session view (only len(fip) traces)
    n_full = len(fip)

    total_plots = n_zoom + n_full
    fig, ax = plt.subplots(total_plots, 1, figsize=(30, 2 * total_plots))
    
    # add title of session_ID and preprocessing type. 

    fig.suptitle(f'{nwb.session_id}: preprocessing = {preprocessing}', fontsize=15)

    ax_zoom = [ax[i] for i in range(len(ax)) if (i + 1) % 2 == 0] + [ax[-1]]
    ax_full =  [ax[i] for i in range(len(ax)) if (i + 1) % 2 == 1][:-1]

    # First call: zoomed view with events + all fip traces
    pss.plot_session_scroller(
        nwb,
        fig=fig,
        ax=ax_zoom,
        plot_list=['go cue', 'bouts', 'manual rewards', 'auto rewards', 'rewarded lick'],
        fip=fip
    )

    # zoom ones should be -50 to 150. 
    for ax in ax_zoom:
        ax.set_xlim(-50, 150)
        ax.set_title('')
        ax.set_ylabel('')
    
    # get xlim, xmax
    xmin = nwb.df_events.iloc[0]["timestamps"]
    x_last = nwb.df_events.iloc[-1]["timestamps"]

    # plot the full trace WITH the snr/kurtosis 
    for (ax, fip_i) in zip(ax_full, fip):
        
        pss.plot_fip(nwb.df_fip, fip_i, ax)

        # set xlim, set ylabel
        ax.set_xlim(xmin, x_last)
        ax.set_ylabel(channel_dict[fip_i[:3]])

        #######  snr, kurtosis #######
        # Get the DataFrame for the current FIP channel
        df_channel = nwb.df_fip.query(f"event == '{fip_i}'")

        # Filter the DataFrame to look at data after time = 0 to 500 seconds before end of trial
        last_timestamps = df_channel.iloc[-1].timestamps - 500
        df_channel_time_filtered = df_channel.query(f"timestamps > 0 and timestamps < {last_timestamps}")
        
        # Extract the trace data as a NumPy array
        channel_trace = df_channel_time_filtered['data'].values

        
        (snr, noise, peaks) = snr_kurtosis.estimate_snr(channel_trace, fps)
        kurtosis = snr_kurtosis.estimate_kurtosis(channel_trace)
        data_cur_stats = f"SNR: {snr:.2f}\nKurtosis: {kurtosis:.2f}"
        ax.text(
            0.98,
            0.95,
            data_cur_stats,
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=18,
            fontweight="bold",
            color="black",
            bbox=dict(facecolor="white", alpha=0.8, edgecolor="none"),
        )
        

    if loc is not None:
        plt.savefig(f'{loc}{nwb.session_id.replace("behavior_","")}_test_plot.png', bbox_inches='tight', transparent=False)
        plt.close(fig)

    return fig, ax