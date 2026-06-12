from pydantic import Field
import os 

from aind_data_schema.base import GenericModel

from analysis_pipeline_utils.metadata import get_metadata_for_records

from analysis_pipeline_utils.analysis_dispatch_model import \
    AnalysisDispatchModel

from analysis_pipeline_utils.utils_analysis_wrapper import (
    run_analysis_jobs)


from data_curation_analysis_model import (DataCurationAnalysisOutputs,
                                    DataCurationAnalysisSpecification)

from hdmf_zarr import NWBZarrIO


ANALYSIS_BUCKET = os.getenv("ANALYSIS_BUCKET")
# logger = logging.getLogger(__name__)

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
    # logger.info(f"Validated channel keys: {list(channel_dict.keys())}")


    # Execute analysis and write to results folder
    # using the passed parameters
    # Example of fetching metadata record from the dispatcher model:
    # Returns a list of records where each record is a dictionary with the metadata. Example below:
    #     metadata_records = get_metadata_for_records(analysis_dispatch_inputs)
    #     first_record = metadata_records[0]
    #     data_description = first_record["data_description"]
    # Example:
    # Use NWBZarrIO to reads
    for location in analysis_dispatch_inputs.file_location:
        with NWBZarrIO(location, 'r') as io:
            nwbfile = io.read()
        

    # nwb processing code
    nwb = nwb_utils_rachel.attach_dfs(nwbfile)

    # plot locations
    plot_loc = '/results/plots/'

    if not os.path.exists(plot_loc):
        os.makedirs(plot_loc)



    # simple analyses. anything more complicated, we should refactor
    (kurtosis, snr) = data_curation_summary_plots.plot_kurtosis_snr_check(nwb, channel_dict, analysis_parameters.preprocessing,
                                            loc = plot_loc)

    output_params = {'kurtosis': kurtosis, 'snr': snr}

    return output_params




if __name__ == "__main__":
    run_analysis_jobs(
        analysis_input_model=AnalysisInputModel,
        analysis_output_model=AnalysisOutputModel,
        run_function=run_analysis
    )

