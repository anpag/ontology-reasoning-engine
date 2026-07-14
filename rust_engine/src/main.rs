use std::env;
use std::fs::File;
use std::io::{self, Write};
use std::collections::HashSet;

use geb_engine::inference::InferenceEngine;
use geb_engine::lpg_exporter::LpgExporter;

fn main() -> io::Result<()> {
    let args: Vec<String> = env::args().collect();
    if args.len() < 5 {
        eprintln!("Usage: geb_engine <format: xml|turtle> <mode: w3c|lpg> <input_file> <output_prefix>");
        std::process::exit(1);
    }

    let format_hint = &args[1];
    let mode = &args[2];
    let input_file = &args[3];
    let output_prefix = &args[4];
    
    let output_nt_file = format!("{}.nt", output_prefix);

    let mut engine = InferenceEngine::new();
    
    if let Err(e) = engine.load_ontology(input_file, format_hint) {
        eprintln!("Failed to load ontology: {}", e);
        std::process::exit(1);
    }

    let inferred_triples = engine.run_inference();

    let mut out = File::create(&output_nt_file)?;
    
    // Output both the original asserted graph and the newly inferred triples
    let mut total_output = engine.kg.triples.clone();
    for t in inferred_triples.clone() {
        total_output.insert(t);
    }
    
    for t in &total_output {
        writeln!(out, "{} <{}> {} .", t.sub, t.pred, t.obj)?;
    }
    println!("Petgraph Materialization Complete. Output {} total triples (including {} inferred).", total_output.len(), inferred_triples.len());

    if mode == "lpg" {
        let output_edges_file = format!("{}_edges.jsonl", output_prefix);
        if let Err(e) = LpgExporter::export_to_jsonl(&total_output, &output_edges_file) {
            eprintln!("Failed to export LPG: {}", e);
            std::process::exit(1);
        }
    }
    
    Ok(())
}
