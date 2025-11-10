# ---------------------
# Standard Library
# ---------------------
import argparse
import glob
import itertools
import json
import warnings
import os

# ---------------------
# Third-Party Libraries
# ---------------------
import numpy as np
import pandas as pd
import requests
import seaborn as sns
import matplotlib
matplotlib.use('Agg')  # Set backend before importing pyplot
import matplotlib.pyplot as plt
import matplotlib as mpl


# ---------------------
# NWB / Domain-Specific Libraries
# ---------------------
from hdmf_zarr import NWBZarrIO
import aind_dynamic_foraging_basic_analysis.licks.annotation as a
from aind_dynamic_foraging_data_utils import nwb_utils, alignment, enrich_dfs
import aind_dynamic_foraging_data_utils.code_ocean_utils as co_utils
from plot import foraging_summary_plots 



# ---------------------
# arguments
# ---------------------

parser = argparse.ArgumentParser()
parser.add_argument('--nwb_filepath', type=str, default=None, help='NWB file path')

parser.add_argument('--saved_loc', type=str, default='/results/', help='Location for saved plots')

parser.add_argument('--channels', type=str, default=None, help='Comma-separated list of channels to plot')

parser.add_argument('--plot_type', type=str, default=None, help='Plot behavior or neural plots')

parser.add_argument('--fitted_model', type=str, default="QLearning_L2F1_CKfull_softmax", help='Model to fit behavior data')

# parser.add_argument('--pdf_save', type=bool, default=False, help='Model to fit behavior data')

args = parser.parse_args()


# if args.pdf_save:
mpl.rcParams['pdf.fonttype'] = 42 # allow text of pdf to be edited in illustrator
mpl.rcParams['font.family'] = 'Arial' 
mpl.rcParams["axes.spines.right"] = False
mpl.rcParams["axes.spines.top"] = False


SAVED_LOC = args.saved_loc


if args.plot_type:
    plot_behavior = 'behavior' in args.plot_type
    plot_neural = 'neural' in args.plot_type
    plot_lick_raster = 'lickraster' in args.plot_type
    plot_baseline = 'baseline' in args.plot_type
else:
    plot_behavior, plot_neural, plot_lick_raster, plot_baseline = True, True, True, True

