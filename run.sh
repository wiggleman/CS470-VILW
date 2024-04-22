#!/bin/bash

# Check if the correct number of arguments are provided
if [ "$#" -ne 3 ]; then
    echo "Usage: ./run.sh </path/to/input.json> </path/to/simple_output.json> </path/to/pip_output.json>"
    exit 1
fi

# Assign the arguments to variables
input_path=$1
simple_output_path=$2
pip_output_path=$3

# Run the Python script with the arguments
python3 src/main.py $input_path $simple_output_path $pip_output_path