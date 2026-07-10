use std::collections::{HashMap, HashSet};
use std::env;
use std::fs::File;
use std::io::{self, BufRead, BufReader, Write};

const SUBCLASS_URI: &str = "<http://www.w3.org/2000/01/rdf-schema#subClassOf>";
const TYPE_URI: &str = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>";
const DOMAIN_URI: &str = "<http://www.w3.org/2000/01/rdf-schema#domain>";
const RANGE_URI: &str = "<http://www.w3.org/2000/01/rdf-schema#range>";
const EQUIV_CLASS_URI: &str = "<http://www.w3.org/2002/07/owl#equivalentClass>";

#[derive(Hash, Eq, PartialEq, Clone)]
struct Triple {
    sub: String,
    pred: String,
    obj: String,
}

fn parse_ntriple(line: &str) -> Option<Triple> {
    let mut parts = line.splitn(3, ' ');
    let sub = parts.next()?;
    let pred = parts.next()?;
    let rest = parts.next()?;
    
    if let Some(dot_idx) = rest.rfind(" .") {
        let obj = &rest[..dot_idx];
        return Some(Triple {
            sub: sub.to_string(),
            pred: pred.to_string(),
            obj: obj.to_string(),
        });
    }
    None
}

fn main() -> io::Result<()> {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        eprintln!("Usage: custom_reasoner_rust <input.nt> <output.nt>");
        std::process::exit(1);
    }

    let input_file = &args[1];
    let output_file = &args[2];

    let file = File::open(input_file)?;
    let reader = BufReader::new(file);

    let mut graph: HashSet<Triple> = HashSet::new();
    let mut subclass_graph: HashMap<String, Vec<String>> = HashMap::new();
    let mut domain_map: HashMap<String, Vec<String>> = HashMap::new();
    let mut range_map: HashMap<String, Vec<String>> = HashMap::new();

    // 1. Read and index the graph
    for line_result in reader.lines() {
        if let Ok(line) = line_result {
            if line.trim().is_empty() { continue; }
            if let Some(t) = parse_ntriple(&line) {
                if t.pred == SUBCLASS_URI {
                    subclass_graph.entry(t.sub.clone()).or_default().push(t.obj.clone());
                } else if t.pred == EQUIV_CLASS_URI {
                    subclass_graph.entry(t.sub.clone()).or_default().push(t.obj.clone());
                    subclass_graph.entry(t.obj.clone()).or_default().push(t.sub.clone());
                } else if t.pred == DOMAIN_URI {
                    domain_map.entry(t.sub.clone()).or_default().push(t.obj.clone());
                } else if t.pred == RANGE_URI {
                    range_map.entry(t.sub.clone()).or_default().push(t.obj.clone());
                }
                graph.insert(t);
            }
        }
    }

    let mut inferred_triples: HashSet<Triple> = HashSet::new();

    // Rule 1: Transitive Closure for SubClassOf (BFS)
    for (start_node, _) in &subclass_graph {
        let mut visited: HashSet<String> = HashSet::new();
        let mut queue: Vec<String> = vec![start_node.clone()];
        visited.insert(start_node.clone());

        let mut head = 0;
        while head < queue.len() {
            let current = queue[head].clone();
            head += 1;

            if let Some(neighbors) = subclass_graph.get(&current) {
                for neighbor in neighbors {
                    // Rust HashSet insert() returns true if the value was NOT present
                    if visited.insert(neighbor.clone()) {
                        queue.push(neighbor.clone());
                        let t = Triple {
                            sub: start_node.clone(),
                            pred: SUBCLASS_URI.to_string(),
                            obj: neighbor.clone(),
                        };
                        if !graph.contains(&t) {
                            inferred_triples.insert(t);
                        }
                    }
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
            if t.obj.starts_with('<') {
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

    // 3. Write inferred triples
    let mut out = File::create(output_file)?;
    for t in &inferred_triples {
        writeln!(out, "{} {} {} .", t.sub, t.pred, t.obj)?;
    }

    println!("Rust Engine Materialization Complete. Inferred {} triples.", inferred_triples.len());
    Ok(())
}
