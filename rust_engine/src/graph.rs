use std::collections::{HashMap, HashSet};
use petgraph::graph::{DiGraph, NodeIndex};

#[derive(Hash, Eq, PartialEq, Clone, Debug)]
pub struct Triple {
    pub sub: String,
    pub pred: String,
    pub obj: String,
}

pub struct KnowledgeGraph {
    pub triples: HashSet<Triple>,
    pub transitive_graphs: HashMap<String, DiGraph<String, ()>>,
    pub transitive_indices: HashMap<String, HashMap<String, NodeIndex>>,
    pub domain_map: HashMap<String, Vec<String>>,
    pub range_map: HashMap<String, Vec<String>>,
    pub inverse_of_map: HashMap<String, String>,
    pub symmetric_props: HashSet<String>,
    pub transitive_props: HashSet<String>,
}

impl KnowledgeGraph {
    pub fn new() -> Self {
        KnowledgeGraph {
            triples: HashSet::new(),
            transitive_graphs: HashMap::new(),
            transitive_indices: HashMap::new(),
            domain_map: HashMap::new(),
            range_map: HashMap::new(),
            inverse_of_map: HashMap::new(),
            symmetric_props: HashSet::new(),
            transitive_props: HashSet::new(),
        }
    }

    pub fn get_or_insert_node(&mut self, uri: &str, pred_uri: &str) -> NodeIndex {
        let g = self.transitive_graphs.entry(pred_uri.to_string()).or_insert_with(DiGraph::new);
        let idx_map = self.transitive_indices.entry(pred_uri.to_string()).or_insert_with(HashMap::new);
        
        if let Some(&idx) = idx_map.get(uri) {
            idx
        } else {
            let idx = g.add_node(uri.to_string());
            idx_map.insert(uri.to_string(), idx);
            idx
        }
    }
}
