#!/usr/bin/env python3
"""
Utility script to convert older Semantic Web formats (RDF/XML, N-Triples, JSON-LD)
into the modern, human-readable Turtle (.ttl) format.
"""

import sys
import argparse
try:
    from rdflib import Graph
except ImportError:
    print("Error: The 'rdflib' package is required. Install it via: pip install rdflib")
    sys.exit(1)

def convert_to_turtle(input_file: str, output_file: str, input_format: str = None):
    g = Graph()
    
    print(f"[*] Reading '{input_file}'...")
    try:
        # If format isn't provided, rdflib will attempt to guess based on the file extension
        g.parse(input_file, format=input_format)
        print(f"[*] Successfully loaded {len(g)} semantic triples.")
    except Exception as e:
        print(f"[!] Error parsing input file: {e}")
        sys.exit(1)
        
    print(f"[*] Converting and serializing to Turtle format...")
    try:
        g.serialize(destination=output_file, format='turtle')
        print(f"[+] Success! Turtle file saved to '{output_file}'")
    except Exception as e:
        print(f"[!] Error saving output file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert legacy RDF/OWL formats to Turtle (.ttl)")
    parser.add_argument("input", help="Path to the input file (e.g., my_ontology.owl, data.xml)")
    parser.add_argument("output", help="Path to the output file (e.g., my_ontology.ttl)")
    parser.add_argument("--format", help="Explicitly specify input format (xml, ntriples, json-ld). If omitted, it is inferred.", default=None)
    
    args = parser.parse_args()
    convert_to_turtle(args.input, args.output, args.format)
