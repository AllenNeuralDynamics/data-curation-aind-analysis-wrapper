import os
import json
import logging
import glob
from pathlib import Path
 
from aind_data_schema.base import GenericModel
 
from analysis_pipeline_utils.metadata import get_metadata_for_records
 
from analysis_pipeline_utils.analysis_dispatch_model import \
    AnalysisDispatchModel
 
from analysis_pipeline_utils.utils_analysis_wrapper import (
    run_analysis_jobs)
 
 
from data_curation_analysis_model import (DataCurationAnalysisOutputs,
                                    DataCurationAnalysisSpecification)
 
from aind_nwb_utils import NWBCombineIO
from hdmf_zarr import NWBZarrIO
from aind_pavlovian_data_utils import pavlovian_analysis as pa
from aind_pavlovian_data_utils.nwb_utils import parse_session_name, create_df_trials
from aind_dynamic_foraging_data_utils import nwb_utils

 
ANALYSIS_BUCKET = os.getenv("ANALYSIS_BUCKET")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
 
# for analysis code
import numpy as np
import pandas as pd
from plots import data_curation_summary_plots
from rachel_analysis_utils import nwb_utils as nwb_utils_rachel
import re
 
 
 
from dotenv import load_dotenv
 
# TODO: use pydantic settings instead
load_dotenv("settings.env")
 
# ======================================================================
# USER MUST EDIT THIS SECTION
#
# 1. Implement  your analysis specification and any output analysis model
# 2. Update the aliases below
#
# Do NOT modify any code outside this section except run_analysis().
# ======================================================================

# supported data types
PAVLOVIAN = "pavlovian"
DYNAMIC_FORAGING = "dynamic_foraging"
VR_FORAGING = "vr_foraging"


VR_FORAGING_ACQUISITION_TYPE = "AindVrForaging"


def _get_acquisition_type(nwb_paths, use_attached_nwb, analysis_dispatch_inputs):
    """Return acquisition.acquisition_type, or None if it can't be found.

    Attached NWBs: read acquisition.json from the attached data asset folder
    (/data/<asset>/acquisition.json).
    Dispatched NWBs: read it from the docdb metadata record.
    """
    try:
        if use_attached_nwb:
            asset_dirs = {Path("/data") / Path(p).relative_to("/data").parts[0]
                          for p in nwb_paths}
            for asset_dir in sorted(asset_dirs):
                acq_file = asset_dir / "acquisition.json"
                if acq_file.exists():
                    with open(acq_file) as f:
                        acq_type = json.load(f).get("acquisition_type")
                    logger.info(f"acquisition_type from {acq_file}: {acq_type}")
                    return acq_type
            logger.warning(f"no acquisition.json found in {sorted(asset_dirs)}")
            return None
        metadata = get_metadata_for_records(analysis_dispatch_inputs)
        acq_type = (metadata[0].get("acquisition") or {}).get("acquisition_type")
        logger.info(f"acquisition_type from docdb metadata: {acq_type}")
        return acq_type
    except Exception as e:
        logger.warning(f"could not get acquisition_type: {e}")
        return None


def _determine_data_type(nwb_paths, use_attached_nwb, analysis_dispatch_inputs):
    """Decide which data type this session is.

    Based on file paths:
       - behavior.nwb.zarr + fib.nwb.zarr          -> PAVLOVIAN
       - single nwb named behavior_*.nwb           -> DYNAMIC_FORAGING
       - single nwb with no behavior_ prefix       -> VR_FORAGING
    """
    # acquisition_type check currently disabled; kept for possible future use
    # acq_type = _get_acquisition_type(nwb_paths, use_attached_nwb, analysis_dispatch_inputs)
    # if acq_type == VR_FORAGING_ACQUISITION_TYPE:
    #     return VR_FORAGING

    fiber_path = next((p for p in nwb_paths if p.endswith("fib.nwb.zarr")), None)
    behavior_path = next((p for p in nwb_paths if p.endswith("behavior.nwb.zarr")), None)
    if fiber_path and behavior_path:
        return PAVLOVIAN

    nwb_files = [p for p in nwb_paths if p.endswith(".nwb")]
    if len(nwb_files) != 1:
        raise ValueError(f"Expected exactly 1 .nwb file, got {nwb_paths}")
    if Path(nwb_files[0]).name.startswith("behavior_"):
        return DYNAMIC_FORAGING
    return VR_FORAGING


def _load_pavlovian_nwb(nwb_paths, preprocessing):
    """Combine the behavior and fiber NWBs and attach pavlovian dataframes."""
    fiber_path = next((p for p in nwb_paths if p.endswith("fib.nwb.zarr")), None)
    behavior_path = next((p for p in nwb_paths if p.endswith("behavior.nwb.zarr")), None)
    if not (fiber_path and behavior_path):
        raise RuntimeError(
            f"Pavlovian loading requires both *behavior.nwb.zarr and *fib.nwb.zarr, got {nwb_paths}"
        )
    logger.info(f"loading {fiber_path}")
    logger.info(f"loading {behavior_path}")
    with NWBCombineIO(behavior_path, [fiber_path]) as (nwbfile, main_io):
        nwbfile = main_io.read()
    df_events, df_fip, meta = pa.load_pavlovian_dfs(nwbfile, preprocessing=preprocessing)
    nwb = nwbfile
    nwb.df_fip = df_fip
    nwb.df_trials = create_df_trials(nwbfile)
    nwb.df_events = df_events
    nwb.meta = meta
    return nwb


def _load_vr_foraging_nwb(nwb_paths):
    """temporary load vr foraging nwb for misconnect checks"""
    errors = {}
    for location in nwb_paths:
        logger.info(f"loading {location}")
        try:
            with NWBZarrIO(location, 'r') as io:
                nwb = io.read()
            df_fip = nwb_utils.create_df_fip(nwb, adjust_time = False)
            # zero timestamps to the first FIP sample as a hack.
            df_fip["timestamps"] = df_fip["timestamps"] - df_fip["timestamps"].iloc[0]
            nwb.df_fip = df_fip
        except Exception as e:
            logger.warning(f"failed to load/attach {location}: {e}")
            errors[location] = e
            continue
        else:
            logger.info(f"successfully loaded {location}")
            return nwb
 
    raise RuntimeError(
        f"Failed to load a usable NWB from any of {nwb_paths}. Errors: {errors}"
    )




def _load_dynamic_foraging_nwb(nwb_paths):
    """Try each path in nwb_paths (in order) until one loads and attaches
    successfully. Returns the attached nwb, or raises RuntimeError with all
    collected errors if every path fails."""
    errors = {}
    for location in nwb_paths:
        logger.info(f"loading {location}")
        try:
            with NWBZarrIO(location, 'r') as io:
                nwbfile = io.read()
            nwb = nwb_utils_rachel.attach_dfs(nwbfile)
        except Exception as e:
            logger.warning(f"failed to load/attach {location}: {e}")
            errors[location] = e
            continue
        else:
            logger.info(f"successfully loaded {location}")
            return nwb
 
    raise RuntimeError(
        f"Failed to load a usable NWB from any of {nwb_paths}. Errors: {errors}"
    )
 
def format_channel_dict_pp(channel_dict, preprocessing, df_fip, logger):
    """
    Build the preprocessing-suffixed channel dict, then filter out any keys
    that don't exist in df_fip['event'], logging a warning for each one dropped.

    Parameters
    ----------
    channel_dict : dict
        Original channel name -> value mapping.
    preprocessing : str
        analysis_parameters.preprocessing value (e.g. "raw", "poly", etc.)
    df_fip : pd.DataFrame
        nwb.df_fip, must have an 'event' column.
    logger : logging.Logger

    Returns
    -------
    dict
        Filtered channel_dict_pp containing only keys present in df_fip['event'].
    """
    if preprocessing == "raw":
        channel_dict_pp = dict(channel_dict)
    else:
        channel_dict_pp = {f"{k}_{preprocessing}": v for k, v in channel_dict.items()}

    valid_events = set(df_fip['event'].unique())
    missing_keys = [k for k in channel_dict_pp if k not in valid_events]
    for k in missing_keys:
        logger.warning(f"'{k}' not found in nwb.df_fip['event']; skipping from channel_dict_pp")

    return {k: v for k, v in channel_dict_pp.items() if k in valid_events}
 
 
AnalysisInputModel = DataCurationAnalysisSpecification
AnalysisOutputModel = DataCurationAnalysisOutputs
 
 
### USER EDITABLE FUNCTION WHERE ANALYSIS IS EXECUTED
def run_analysis(
    analysis_dispatch_inputs: AnalysisDispatchModel,
    analysis_parameters: AnalysisInputModel
) -> dict | None:
 
    # parse parameters and validate them
    channel_dict = analysis_parameters.channels
    # require keys of the form G|R|Iso followed by _ and a digit 0-4 (e.g. "G_0", "R_3", "Iso_2")
    pattern = re.compile(r"^(?:G|R|Iso)_[0-4]$")
    invalid = [k for k in channel_dict.keys() if not pattern.match(str(k))]
    if invalid:
        raise ValueError(f"Invalid channel keys (must match G/R/Iso_0-4): {invalid}")
    logger.info(f"Validated channel keys: {list(channel_dict.keys())}")
 
 
    # Execute analysis and write to results folder
    # using the passed parameters
    # Example of fetching metadata record from the dispatcher model:
    # Returns a list of records where each record is a dictionary with the metadata. Example below:
    #     metadata_records = get_metadata_for_records(analysis_dispatch_inputs)
    #     first_record = metadata_records[0]
    #     data_description = first_record["data_description"]
    nwb_paths = analysis_dispatch_inputs.file_location
    if analysis_parameters.use_attached_nwb:
        logger.info("Skipping dispatch job file, using attached NWBs")
        nwb_paths = sorted(
            set(glob.glob("/data/*/nwb/*.nwb"))
            | set(glob.glob("/data/behavior*/*.nwb.zarr"))
        )

    data_type = _determine_data_type(
        nwb_paths, analysis_parameters.use_attached_nwb, analysis_dispatch_inputs)
    logger.info(f"data type: {data_type}")

    if data_type == PAVLOVIAN:
        nwb = _load_pavlovian_nwb(nwb_paths, analysis_parameters.preprocessing)
    elif data_type == DYNAMIC_FORAGING:
        nwb = _load_dynamic_foraging_nwb(nwb_paths)
    elif data_type == VR_FORAGING:
        nwb = _load_vr_foraging_nwb(nwb_paths)
    else:
        raise ValueError(f"Unknown data type: {data_type}")

    logger.info(f"loaded NWB : {nwb.session_id}")
    # plot locations
    plot_loc = '/results/individual_plots/'
    aggregate_loc = '/results/aggregate_results/'

    for path in [plot_loc, aggregate_loc]:
        if not os.path.exists(path):
            os.makedirs(path)

    session_id = nwb.session_id.replace("behavior_","")

    # data curation summary (all data types)
    channel_dict_pp = format_channel_dict_pp(
            channel_dict, analysis_parameters.preprocessing, nwb.df_fip, logger
        )
    df_data_curation_vals = data_curation_summary_plots.get_df_data_curation(nwb, channel_dict_pp)
    df_data_curation_vals.to_csv(f'{aggregate_loc}{session_id}.csv', index=False)

    # plots (not available for vr_foraging)
    if data_type in (PAVLOVIAN, DYNAMIC_FORAGING):
        pav_flag = data_type == PAVLOVIAN
        data_curation_summary_plots.plot_data_curation_plotly(nwb, channel_dict_pp, df_data_curation_vals, analysis_parameters.preprocessing,
             pav_flag, loc = plot_loc)
        data_curation_summary_plots.plot_data_curation(nwb, channel_dict_pp, df_data_curation_vals, analysis_parameters.preprocessing,
             pav_flag, loc = plot_loc)
    # save nwb so i can make lifetime plots later. a bit of a hack to get the ses_idx
    print(f"now saving {nwb.session_id}")
    nwb.df_fip = nwb.df_fip[::50]
    nwb.df_fip.to_parquet(f'{aggregate_loc}{session_id}_df_fip.parquet')

    print(f"save_complete")
 
    return {}
 
 
 
 
if __name__ == "__main__":
    run_analysis_jobs(
        analysis_input_model=AnalysisInputModel,
        analysis_output_model=AnalysisOutputModel,
        run_function=run_analysis
    )
 