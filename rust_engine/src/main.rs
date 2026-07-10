use std::collections::{HashMap, HashSet};
use std::env;
use std::fs::File;
use std::io::{self, BufReader, Write};

use oxrdfxml::RdfXmlParser;
use oxttl::TurtleParser;
use petgraph::graph::{DiGraph, NodeIndex};
use petgraph::visit::Bfs;

const SUBCLASS_URI: &str = "http://www.w3.org/2000/01/rdf-schema#subClassOf";
const TYPE_URI: &str = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";
const DOMAIN_URI: &str = "http://www.w3.org/2000/01/rdf-schema#domain";
const RANGE_URI: &str = "http://www.w3.org/2000/01/rdf-schema#range";
const EQUIV_CLASS_URI: &str = "http://www.w3.org/2002/07/owl#equivalentClass";

#[derive(Hash, Eq, PartialEq, Clone)]
struct Triple {
    sub: String,
    pred: String,
    obj: String,
}

fn main() -> io::Result<()> {
    let args: Vec<String> = env::args().collect();
    if args.len() < 4 {
        eprintln!("Usage: custom_reasoner_rust <format: xml|turtle> <input_file> <output.nt>");
        std::process::exit(1);
    }

    let format = &args[1];
    let input_file = &args[2];
    let output_file = &args[3];

    let mut graph: HashSet<Triple> = HashSet::new();
    
    // Replace manual BFS HashMaps with scalable petgraph representation
    let mut subclass_graph = DiGraph::<String, ()>::new();
    let mut node_indices: HashMap<String, NodeIndex> = HashMap::new();
    
    let mut domain_map: HashMap<String, Vec<String>> = HashMap::new();
    let mut range_map: HashMap<String, Vec<String>> = HashMap::new();

    let mut get_or_insert_node = |uri: &str, graph_ref: &mut DiGraph<String, ()>, indices: &mut HashMap<String, NodeIndex>| -> NodeIndex {
        if let Some(&idx) = indices.get(uri) {
            idx
        } else {
            let idx = graph_ref.add_node(uri.to_string());
            indices.insert(uri.to_string(), idx);
            idx
        }
    };

    let file = File::open(input_file)?;
    let reader = BufReader::new(file);

    // 1. Natively parse using Oxigraph's blazing fast micro-crates
    if format == "xml" {
        for triple_res in RdfXmlParser::new().for_reader(reader) {
            if let Ok(t_ox) = triple_res {
                let sub = t_ox.subject.to_string();
                let pred = t_ox.predicate.as_str().to_string();
                let obj = t_ox.object.to_string();

                let t = Triple { sub: sub.clone(), pred: pred.clone(), obj: obj.clone() };
                
                if pred == SUBCLASS_URI {
                    let sub_idx = get_or_insert_node(&sub, &mut subclass_graph, &mut node_indices);
                    let obj_idx = get_or_insert_node(&obj, &mut subclass_graph, &mut node_indices);
                    subclass_graph.add_edge(sub_idx, obj_idx, ());
                } else if pred == EQUIV_CLASS_URI {
                    let sub_idx = get_or_insert_node(&sub, &mut subclass_graph, &mut node_indices);
                    let obj_idx = get_or_insert_node(&obj, &mut subclass_graph, &mut node_indices);
                    subclass_graph.add_edge(sub_idx, obj_idx, ());
                    subclass_graph.add_edge(obj_idx, sub_idx, ());
                } else if pred == DOMAIN_URI {
                    domain_map.entry(sub.clone()).or_default().push(obj.clone());
                } else if pred == RANGE_URI {
                    range_map.entry(sub.clone()).or_default().push(obj.clone());
                }
                graph.insert(t);
            }
        }
    } else if format == "turtle" {
        for triple_res in TurtleParser::new().for_reader(reader) {
            if let Ok(t_ox) = triple_res {
                let sub = t_ox.subject.to_string();
                let pred = t_ox.predicate.as_str().to_string();
                let obj = t_ox.object.to_string();

                let t = Triple { sub: sub.clone(), pred: pred.clone(), obj: obj.clone() };
                
                if pred == SUBCLASS_URI {
                    let sub_idx = get_or_insert_node(&sub, &mut subclass_graph, &mut node_indices);
                    let obj_idx = get_or_insert_node(&obj, &mut subclass_graph, &mut node_indices);
                    subclass_graph.add_edge(sub_idx, obj_idx, ());
                } else if pred == EQUIV_CLASS_URI {
                    let sub_idx = get_or_insert_node(&sub, &mut subclass_graph, &mut node_indices);
                    let obj_idx = get_or_insert_node(&obj, &mut subclass_graph, &mut node_indices);
                    subclass_graph.add_edge(sub_idx, obj_idx, ());
                    subclass_graph.add_edge(obj_idx, sub_idx, ());
                } else if pred == DOMAIN_URI {
                    domain_map.entry(sub.clone()).or_default().push(obj.clone());
                } else if pred == RANGE_URI {
                    range_map.entry(sub.clone()).or_default().push(obj.clone());
                }
                graph.insert(t);
            }
        }
    }

    println!("Graph successfully parsed. Triples: {}", graph.len());

    let mut inferred_triples: HashSet<Triple> = HashSet::new();

    // Rule 1: Transitive Closure for SubClassOf (Petgraph BFS)
    for start_idx in subclass_graph.node_indices() {
        let mut bfs = Bfs::new(&subclass_graph, start_idx);
        let start_node_uri = subclass_graph.node_weight(start_idx).unwrap().clone();
        
        while let Some(visited_idx) = bfs.next(&subclass_graph) {
            if visited_idx != start_idx {
                let visited_uri = subclass_graph.node_weight(visited_idx).unwrap().clone();
                let t = Triple {
                    sub: start_node_uri.clone(),
                    pred: SUBCLASS_URI.to_string(),
                    obj: visited_uri,
                };
                if !graph.contains(&t) {
                    inferred_triples.insert(t);
                }
            }
        }
    }

    // Rules 2 & 3: Domain and Range Type Inference
    for t in &graph {
        if let Some(domains) = domain_map.get(&t.pred) {
            for dom in domains {
                let inf_t = Triple {
                    sub: t.sub.clone(),
                    pred: TYPE_URI.to_string(),
                    obj: dom.clone(),
                };
                if !graph.contains(&inf_t) {
                    inferred_triples.insert(inf_t);
                }
            }
        }
        if let Some(ranges) = range_map.get(&t.pred) {
            if !t.obj.starts_with('"') {
                for ran in ranges {
                    let inf_t = Triple {
                        sub: t.obj.clone(),
                        pred: TYPE_URI.to_string(),
                        obj: ran.clone(),
                    };
                    if !graph.contains(&inf_t) {
                        inferred_triples.insert(inf_t);
                    }
                }
            }
        }
    }

    // 3. Write inferred triples out
    let mut out = File::create(output_file)?;
    for t in &inferred_triples {
        writeln!(out, "{} <{}> {} .", t.sub, t.pred, t.obj)?;
    }

    println!("Petgraph Materialization Complete. Inferred {} triples.", inferred_triples.len());
    Ok(())
}
