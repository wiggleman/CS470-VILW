import argparse
import json
from VLIW470 import VLIW470



if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='parse command line arguments')
    parser.add_argument('input_path', type=str, help='Input file path')
    parser.add_argument('simple_output_path', type=str, help='Output file path1')
    parser.add_argument('pip_output_path', type=str, help='Output file path2')

    args = parser.parse_args()

    main(args.input_path, args.simple_output_path, args.pip_output_path)


def main(input_path, simple_output_path, pip_output_path):
    with open(input_path, 'r') as f:
        insts = json.load(f)

    VLIW470(insts)


    

    with open(simple_output_path, 'w') as f:
        json.dump(simple_data, f)

    with open(pip_output_path, 'w') as f:
        json.dump(pip_data, f)