use std::collections::{HashMap, HashSet};
use std::env;
use std::fs;
use std::fs::File;
use std::io::{self, Cursor, Write};

use oxrdfxml::RdfXmlParser;
use oxttl::TurtleParser;
use petgraph::graph::{DiGraph, NodeIndex};
use petgraph::visit::Bfs;
use reqwest;
use serde_json::{json, Map, Value};

const SUBCLASS_URI: &str = "http://www.w3.org/2000/01/rdf-schema#subClassOf";
const TYPE_URI: &str = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";
const DOMAIN_URI: &str = "http://www.w3.org/2000/01/rdf-schema#domain";
const RANGE_URI: &str = "http://www.w3.org/2000/01/rdf-schema#range";
const EQUIV_CLASS_URI: &str = "http://www.w3.org/2002/07/owl#equivalentClass";
// Phase 1: OWL 2 RL / EL Inference Profiles
const INVERSE_OF_URI: &str = "http://www.w3.org/2002/07/owl#inverseOf";
const SYMMETRIC_PROP_URI: &str = "http://www.w3.org/2002/07/owl#SymmetricProperty";
const TRANSITIVE_PROP_URI: &str = "http://www.w3.org/2002/07/owl#TransitiveProperty";
// Phase 2: Modular Modeling & eXtreme Design
const IMPORTS_URI: &str = "http://www.w3.org/2002/07/owl#imports";
// Phase 3: N-ary Relations / BigQuery LPG Flattening
const STATEMENT_URI: &str = "http://www.w3.org/1999/02/22-rdf-syntax-ns#Statement";
const SUBJECT_URI: &str = "http://www.w3.org/1999/02/22-rdf-syntax-ns#subject";
const PREDICATE_URI: &str = "http://www.w3.org/1999/02/22-rdf-syntax-ns#predicate";
const OBJECT_URI: &str = "http://www.w3.org/1999/02/22-rdf-syntax-ns#object";

#[derive(Hash, Eq, PartialEq, Clone)]
struct Triple {
    sub: String,
    pred: String,
    obj: String,
}

fn get_or_insert_node(uri: &str, graph_ref: &mut DiGraph<String, ()>, indices: &mut HashMap<String, NodeIndex>) -> NodeIndex {
    if let Some(&idx) = indices.get(uri) {
        idx
    } else {
        let idx = graph_ref.add_node(uri.to_string());
        indices.insert(uri.to_string(), idx);
        idx
    }
}

fn process_triple(
    sub: String, 
    pred: String, 
    obj: String, 
    graph: &mut HashSet<Triple>,
    transitive_graphs: &mut HashMap<String, DiGraph<String, ()>>,
    transitive_indices: &mut HashMap<String, HashMap<String, NodeIndex>>,
    domain_map: &mut HashMap<String, Vec<String>>,
    range_map: &mut HashMap<String, Vec<String>>,
    inverse_of_map: &mut HashMap<String, String>,
    symmetric_props: &mut HashSet<String>,
    transitive_props: &mut HashSet<String>,
) {
    let t = Triple { sub: sub.clone(), pred: pred.clone(), obj: obj.clone() };
    
    // Core TBox Pattern Extraction
    if pred == SUBCLASS_URI {
        let g = transitive_graphs.entry(SUBCLASS_URI.to_string()).or_insert_with(DiGraph::new);
        let idx_map = transitive_indices.entry(SUBCLASS_URI.to_string()).or_insert_with(HashMap::new);
        let sub_idx = get_or_insert_node(&sub, g, idx_map);
        let obj_idx = get_or_insert_node(&obj, g, idx_map);
        g.add_edge(sub_idx, obj_idx, ());
    } else if pred == EQUIV_CLASS_URI {
        let g = transitive_graphs.entry(SUBCLASS_URI.to_string()).or_insert_with(DiGraph::new);
        let idx_map = transitive_indices.entry(SUBCLASS_URI.to_string()).or_insert_with(HashMap::new);
        let sub_idx = get_or_insert_node(&sub, g, idx_map);
        let obj_idx = get_or_insert_node(&obj, g, idx_map);
        g.add_edge(sub_idx, obj_idx, ());
        g.add_edge(obj_idx, sub_idx, ());
    } else if pred == DOMAIN_URI {
        domain_map.entry(sub.clone()).or_default().push(obj.clone());
    } else if pred == RANGE_URI {
        range_map.entry(sub.clone()).or_default().push(obj.clone());
    } else if pred == INVERSE_OF_URI {
        inverse_of_map.insert(sub.clone(), obj.clone());
        inverse_of_map.insert(obj.clone(), sub.clone());
    } else if pred == TYPE_URI && obj == format!("<{}>", SYMMETRIC_PROP_URI) {
        symmetric_props.insert(sub.clone());
    } else if pred == TYPE_URI && obj == format!("<{}>", TRANSITIVE_PROP_URI) {
        transitive_props.insert(sub.clone());
    }
    
    graph.insert(t);
}

fn parse_content(
    content: &[u8],
    format_hint: &str,
    graph: &mut HashSet<Triple>,
    transitive_graphs: &mut HashMap<String, DiGraph<String, ()>>,
    transitive_indices: &mut HashMap<String, HashMap<String, NodeIndex>>,
    domain_map: &mut HashMap<String, Vec<String>>,
    range_map: &mut HashMap<String, Vec<String>>,
    inverse_of_map: &mut HashMap<String, String>,
    symmetric_props: &mut HashSet<String>,
    transitive_props: &mut HashSet<String>,
    imports_queue: &mut Vec<String>,
) {
    let mut try_parse = |is_xml: bool| -> bool {
        let mut success = false;
        let reader = Cursor::new(content);
        if is_xml {
            for triple_res in RdfXmlParser::new().for_reader(reader) {
                if let Ok(t_ox) = triple_res {
                    success = true;
                    let sub = t_ox.subject.to_string();
                    let pred = t_ox.predicate.as_str().to_string();
                    let obj = t_ox.object.to_string();
                    
                    if pred == IMPORTS_URI {
                        let clean_url = obj.trim_start_matches('<').trim_end_matches('>').to_string();
                        imports_queue.push(clean_url);
                    }
                    process_triple(sub, pred, obj, graph, transitive_graphs, transitive_indices, domain_map, range_map, inverse_of_map, symmetric_props, transitive_props);
                }
            }
        } else {
            for triple_res in TurtleParser::new().for_reader(reader) {
                if let Ok(t_ox) = triple_res {
                    success = true;
                    let sub = t_ox.subject.to_string();
                    let pred = t_ox.predicate.as_str().to_string();
                    let obj = t_ox.object.to_string();
                    
                    if pred == IMPORTS_URI {
                        let clean_url = obj.trim_start_matches('<').trim_end_matches('>').to_string();
                        imports_queue.push(clean_url);
                    }
                    process_triple(sub, pred, obj, graph, transitive_graphs, transitive_indices, domain_map, range_map, inverse_of_map, symmetric_props, transitive_props);
                }
            }
        }
        success
    };

    let first_try = if format_hint == "xml" { true } else { false };
    if !try_parse(first_try) {
        try_parse(!first_try);
    }
}

fn main() -> io::Result<()> {
    let args: Vec<String> = env::args().collect();
    if args.len() < 5 {
        eprintln!("Usage: custom_reasoner_rust <format: xml|turtle> <mode: w3c|lpg> <input_file> <output_prefix>");
        std::process::exit(1);
    }

    let format = &args[1];
    let mode = &args[2];
    let input_file = &args[3];
    let output_prefix = &args[4];
    
    let output_nt_file = format!("{}.nt", output_prefix);

    let mut graph: HashSet<Triple> = HashSet::new();
    let mut transitive_graphs: HashMap<String, DiGraph<String, ()>> = HashMap::new();
    let mut transitive_indices: HashMap<String, HashMap<String, NodeIndex>> = HashMap::new();
    let mut domain_map: HashMap<String, Vec<String>> = HashMap::new();
    let mut range_map: HashMap<String, Vec<String>> = HashMap::new();
    let mut inverse_of_map: HashMap<String, String> = HashMap::new();
    let mut symmetric_props: HashSet<String> = HashSet::new();
    let mut transitive_props: HashSet<String> = HashSet::new();
    transitive_props.insert(SUBCLASS_URI.to_string());

    let mut imports_queue: Vec<String> = Vec::new();
    let mut visited_urls: HashSet<String> = HashSet::new();

    let content = fs::read(input_file)?;
    println!("Parsing root file: {}", input_file);
    parse_content(
        &content, format, &mut graph, &mut transitive_graphs, &mut transitive_indices,
        &mut domain_map, &mut range_map, &mut inverse_of_map, &mut symmetric_props, &mut transitive_props, &mut imports_queue
    );
    
    while let Some(url) = imports_queue.pop() {
        if visited_urls.contains(&url) { continue; }
        visited_urls.insert(url.clone());
        println!("Resolving imported module: {}", url);
        
        let fetched_content = if url.starts_with("http") {
            match reqwest::blocking::get(&url) {
                Ok(resp) => resp.bytes().unwrap_or_default().to_vec(),
                Err(e) => {
                    eprintln!("Failed to fetch {}: {}", url, e);
                    continue;
                }
            }
        } else {
            match fs::read(&url) {
                Ok(b) => b,
                Err(e) => {
                    eprintln!("Failed to read local import {}: {}", url, e);
                    continue;
                }
            }
        };

        parse_content(
            &fetched_content, "xml", &mut graph, &mut transitive_graphs, &mut transitive_indices,
            &mut domain_map, &mut range_map, &mut inverse_of_map, &mut symmetric_props, &mut transitive_props, &mut imports_queue
        );
    }

    println!("Modular parsing complete. Unified Graph Triples: {}", graph.len());

    for t in &graph {
        let pred_with_brackets = format!("<{}>", t.pred);
        if transitive_props.contains(&pred_with_brackets) && t.pred != SUBCLASS_URI {
            let g = transitive_graphs.entry(t.pred.clone()).or_insert_with(DiGraph::new);
            let idx_map = transitive_indices.entry(t.pred.clone()).or_insert_with(HashMap::new);
            let sub_idx = get_or_insert_node(&t.sub, g, idx_map);
            let obj_idx = get_or_insert_node(&t.obj, g, idx_map);
            g.add_edge(sub_idx, obj_idx, ());
        }
    }

    let mut inferred_triples: HashSet<Triple> = HashSet::new();

    for (pred_uri, g) in &transitive_graphs {
        for start_idx in g.node_indices() {
            let mut bfs = Bfs::new(g, start_idx);
            let start_node_uri = g.node_weight(start_idx).unwrap().clone();
            
            while let Some(visited_idx) = bfs.next(g) {
                if visited_idx != start_idx {
                    let visited_uri = g.node_weight(visited_idx).unwrap().clone();
                    let t = Triple {
                        sub: start_node_uri.clone(),
                        pred: pred_uri.clone(),
                        obj: visited_uri,
                    };
                    if !graph.contains(&t) {
                        inferred_triples.insert(t);
                    }
                }
            }
        }
    }

    for t in &graph {
        let pred_with_brackets = format!("<{}>", t.pred);
        if let Some(domains) = domain_map.get(&pred_with_brackets) {
            for dom in domains {
                let inf_t = Triple { sub: t.sub.clone(), pred: TYPE_URI.to_string(), obj: dom.clone() };
                if !graph.contains(&inf_t) { inferred_triples.insert(inf_t); }
            }
        }
        if let Some(ranges) = range_map.get(&pred_with_brackets) {
            if !t.obj.starts_with('"') {
                for ran in ranges {
                    let inf_t = Triple { sub: t.obj.clone(), pred: TYPE_URI.to_string(), obj: ran.clone() };
                    if !graph.contains(&inf_t) { inferred_triples.insert(inf_t); }
                }
            }
        }
        if symmetric_props.contains(&pred_with_brackets) {
            let inf_t = Triple { sub: t.obj.clone(), pred: t.pred.clone(), obj: t.sub.clone() };
            if !graph.contains(&inf_t) { inferred_triples.insert(inf_t); }
        }
        if let Some(inv_pred) = inverse_of_map.get(&pred_with_brackets) {
            let clean_inv_pred = inv_pred.trim_start_matches('<').trim_end_matches('>').to_string();
            let inf_t = Triple { sub: t.obj.clone(), pred: clean_inv_pred, obj: t.sub.clone() };
            if !graph.contains(&inf_t) { inferred_triples.insert(inf_t); }
        }
    }

    let mut out = File::create(&output_nt_file)?;
    for t in &inferred_triples {
        writeln!(out, "{} <{}> {} .", t.sub, t.pred, t.obj)?;
    }
    println!("Petgraph Materialization Complete. Inferred {} triples.", inferred_triples.len());

    if mode == "lpg" {
        // Phase 3: BigQuery Labeled Property Graph (LPG) Generation
        // Translate standard RDF Reification patterns into rich JSON-L edges
        let mut total_graph: HashSet<Triple> = graph.clone();
        for t in inferred_triples {
            total_graph.insert(t);
        }

        let statement_type_obj = format!("<{}>", STATEMENT_URI);
        let mut statement_subjects: HashSet<String> = HashSet::new();
        for t in &total_graph {
            if t.pred == TYPE_URI && t.obj == statement_type_obj {
                statement_subjects.insert(t.sub.clone());
            }
        }

        let output_edges_file = format!("{}_edges.jsonl", output_prefix);
        let mut edges_out = File::create(&output_edges_file)?;
        let mut flattened_edges_count = 0;

        for s in &statement_subjects {
            let mut src = String::new();
            let mut edge_label = String::new();
            let mut dst = String::new();
            let mut properties = Map::new();

            for t in &total_graph {
                if t.sub == *s {
                    if t.pred == SUBJECT_URI {
                        src = t.obj.clone();
                    } else if t.pred == PREDICATE_URI {
                        edge_label = t.obj.clone();
                    } else if t.pred == OBJECT_URI {
                        dst = t.obj.clone();
                    } else if t.pred != TYPE_URI {
                        // It's a property on the edge
                        properties.insert(t.pred.clone(), json!(t.obj));
                    }
                }
            }

            if !src.is_empty() && !edge_label.is_empty() && !dst.is_empty() {
                let edge_json = json!({
                    "src": src,
                    "edge_label": edge_label,
                    "dst": dst,
                    "properties": properties
                });
                writeln!(edges_out, "{}", edge_json.to_string())?;
                flattened_edges_count += 1;
            }
        }
        println!("BigQuery LPG Flattening Complete. Generated {} rich edges.", flattened_edges_count);
    }
    
    Ok(())
}
