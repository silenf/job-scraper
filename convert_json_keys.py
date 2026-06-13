#!/usr/bin/env python3
import argparse
import json
import os
import sys

def lowercase_keys(data):
    """Recursively converts all keys in a JSON structure to lowercase, keeping values intact."""
    if isinstance(data, dict):
        return {str(k).lower(): lowercase_keys(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [lowercase_keys(item) for item in data]
    else:
        return data

def main():
    parser = argparse.ArgumentParser(description="Utility script to recursively convert all keys in a JSON file to lowercase.")
    parser.add_argument("input_file", help="Path to the input JSON file to convert")
    parser.add_argument("-o", "--output", help="Path to write the output JSON file. If omitted, overwrites the input file in-place.")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input_file):
        print(f"Error: Input file '{args.input_file}' does not exist.")
        sys.exit(1)
        
    # Load input JSON
    try:
        with open(args.input_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading or parsing JSON file '{args.input_file}': {e}")
        sys.exit(1)
        
    print(f"Converting keys to lowercase for '{args.input_file}'...")
    converted_data = lowercase_keys(data)
    
    # Resolve output path
    output_path = args.output if args.output else args.input_file
    
    # Save output JSON
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(converted_data, f, indent=2, ensure_ascii=False)
        print(f"Successfully saved converted JSON to '{output_path}'.")
    except Exception as e:
        print(f"Error writing to output file '{output_path}': {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
