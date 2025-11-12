    # processing.output_parameters = ExampleAnalysisOutputs(
    #     isi_violations=["example_violation_1", "example_violation_2"],
    #     additional_info=(
    #         "This is an example of additional information about the analysis."
    #     )[0],
    # )

    
# running subprocesses
subprocess.run(["--param_1": parameters["param_1"]])


logger.info(f"{location}")
cmd = [
    "python", 
    "analysis_wrapper/run_summary_plots_individual.py",
    "--nwb_filepath", location, 
    "--channels", parameters['channels'], # should be placed in CSV eventuallys
    "--plot_type", parameters['plot_types'],
    "--fitted_model", parameters["fitted_model"] #,
    # "--pdf_save", parameters["pdf_save"]
    # Add other arguments here if needed
]
print(f"Running: {' '.join(cmd)}")
try:
    subprocess.run(cmd, check=True, capture_output=True, text=True)
# except Exception as e:
#     print(f"Error processing {location}: {e}")
except subprocess.CalledProcessError as e:
    print(f"\ Error processing {location}")
    print(f"Command: {e.cmd}")
    print(f"Return code: {e.returncode}")
    print(f"\nSTDOUT:\n{e.stdout}")
    print(f"\nSTDERR:\n{e.stderr}")


