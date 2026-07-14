use std::collections::HashSet;
use std::fs::File;
use std::io::{self, Write};
use serde_json::{json, Map};

use crate::graph::Triple;
use crate::inference::TYPE_URI;

const STATEMENT_URI: &str = "http://www.w3.org/1999/02/22-rdf-syntax-ns#Statement";
const SUBJECT_URI: &str = "http://www.w3.org/1999/02/22-rdf-syntax-ns#subject";
const PREDICATE_URI: &str = "http://www.w3.org/1999/02/22-rdf-syntax-ns#predicate";
const OBJECT_URI: &str = "http://www.w3.org/1999/02/22-rdf-syntax-ns#object";

pub struct LpgExporter;

impl LpgExporter {
    pub fn export_to_jsonl(total_graph: &HashSet<Triple>, output_file: &str) -> io::Result<()> {
        let statement_type_obj = format!("<{}>", STATEMENT_URI);
        let mut statement_subjects: HashSet<String> = HashSet::new();
        
        for t in total_graph {
            if t.pred == TYPE_URI && t.obj == statement_type_obj {
                statement_subjects.insert(t.sub.clone());
            }
        }

        let mut edges_out = File::create(output_file)?;
        let mut flattened_edges_count = 0;

        for s in &statement_subjects {
            let mut src = String::new();
            let mut edge_label = String::new();
            let mut dst = String::new();
            let mut properties = Map::new();

            for t in total_graph {
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
        Ok(())
    }
}
