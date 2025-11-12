import json
import logging
import os

from analysis_pipeline_utils.analysis_dispatch_model import \
    AnalysisDispatchModel
from analysis_pipeline_utils.metadata import (construct_processing_record,
                                              docdb_record_exists,
                                              write_results_and_metadata)
from analysis_pipeline_utils.utils_analysis_wrapper import (
    get_analysis_model_parameters, make_cli_model)

from data_curation_analysis_model import (DataCurationAnalysisOutputs,
                                    DataCurationAnalysisSpecification)

from hdmf_zarr import NWBZarrIO


ANALYSIS_BUCKET = os.getenv("ANALYSIS_BUCKET")
logger = logging.getLogger(__name__)

# for analysis code
import numpy as np
import pandas as pd 
from plots import data_curation_summary_plots
from utils import nwb_utils as nwb_utils_rachel
import re


def run_analysis(
    analysis_dispatch_inputs: AnalysisDispatchModel,
    dry_run: bool = True,
    **parameters,
) -> None:
    """
    Runs the analysis

    Parameters
    ----------
    analysis_dispatch_inputs: AnalysisDispatchModel
        The input model with input data
        from dispatcher

    dry_run: bool, Default True
        Dry run of analysis. If true,
        does not post results

    parameters
        The analysis model parameters

    """
    processing = construct_processing_record(
        analysis_dispatch_inputs, **parameters
    )
    if docdb_record_exists(processing):
        logger.info("Record already exists, skipping.")
        return

    # parse parameters and validate them
    channel_dict = parameters["channels"]
    # require keys of the form G|R|Iso followed by _ and a digit 0-4 (e.g. "G_0", "R_3", "Iso_2")
    pattern = re.compile(r"^(?:G|R|Iso)_[0-4]$")
    invalid = [k for k in channel_dict.keys() if not pattern.match(str(k))]
    if invalid:
        raise ValueError(f"Invalid channel keys (must match G/R/Iso_0-4): {invalid}")
    logger.info(f"Validated channel keys: {list(channel_dict.keys())}")

    # Execute analysis and write to results folder
    # using the passed parameters
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
    data_curation_summary_plots.plot_kurtosis_snr_check(nwb, channel_dict, 
                                            loc = plot_loc)



    if not dry_run:
        logger.info("Running analysis and posting results")
        write_results_and_metadata(processing, ANALYSIS_BUCKET)
        logger.info("Successfully wrote record to docdb and s3")
    else:
        logger.info("Dry run complete. Results not posted")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    cli_cls = make_cli_model(DataCurationAnalysisSpecification)
    cli_model = cli_cls()
    logger.info(f"Command line args {cli_model.model_dump()}")
    
    input_model_paths = tuple(cli_model.input_directory.glob("job_dict/*")) # how should i set this as? 
    logger.info(
        f"Found {len(input_model_paths)} input job models to run analysis on."
    )

    for model_path in input_model_paths:
        with open(model_path, "r") as f:
            analysis_dispatch_inputs = AnalysisDispatchModel.model_validate(
                json.load(f)
            )
        merged_parameters = get_analysis_model_parameters(
            analysis_dispatch_inputs,
            cli_model,
            DataCurationAnalysisSpecification,
            analysis_parameters_json_path=cli_model.input_directory
            / "analysis_parameters.json",
        )
        analysis_specification = DataCurationAnalysisSpecification.model_validate(
            merged_parameters
        ).model_dump()
        logger.info(f"Running with analysis specs {analysis_specification}")
        run_analysis(
            analysis_dispatch_inputs,
            bool(cli_model.dry_run),
            **analysis_specification,
        )