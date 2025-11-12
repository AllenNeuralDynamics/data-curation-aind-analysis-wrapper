import numpy as np
import pandas as pd 
from utils import analysis_util
from aind_dynamic_foraging_data_utils import nwb_utils, alignment, enrich_dfs



def attach_dfs(nwb_file):

    nwb_file.df_events = nwb_utils.create_df_events(nwb_file)
    nwb_file.df_fip = nwb_utils.create_df_fip(nwb_file)
    nwb_file.df_trials = nwb_utils.create_df_trials(nwb_file)

    return nwb_file