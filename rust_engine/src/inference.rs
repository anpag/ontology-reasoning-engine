use std::collections::HashSet;
use std::fs;
use std::io::Cursor;
use oxrdfxml::RdfXmlParser;
use oxttl::TurtleParser;
use petgraph::visit::Bfs;

use crate::graph::{KnowledgeGraph, Triple};

pub const SUBCLASS_URI: &str = "http://www.w3.org/2000/01/rdf-schema#subClassOf";
pub const TYPE_URI: &str = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";
pub const DOMAIN_URI: &str = "http://www.w3.org/2000/01/rdf-schema#domain";
pub const RANGE_URI: &str = "http://www.w3.org/2000/01/rdf-schema#range";
pub const EQUIV_CLASS_URI: &str = "http://www.w3.org/2002/07/owl#equivalentClass";
pub const INVERSE_OF_URI: &str = "http://www.w3.org/2002/07/owl#inverseOf";
pub const SYMMETRIC_PROP_URI: &str = "http://www.w3.org/2002/07/owl#SymmetricProperty";
pub const TRANSITIVE_PROP_URI: &str = "http://www.w3.org/2002/07/owl#TransitiveProperty";
pub const IMPORTS_URI: &str = "http://www.w3.org/2002/07/owl#imports";

pub struct InferenceEngine {
    pub kg: KnowledgeGraph,
}

impl InferenceEngine {
    pub fn new() -> Self {
        let mut kg = KnowledgeGraph::new();
        kg.transitive_props.insert(SUBCLASS_URI.to_string());
        InferenceEngine { kg }
    }

    pub fn process_triple(&mut self, sub: String, pred: String, obj: String) {
        let t = Triple { sub: sub.clone(), pred: pred.clone(), obj: obj.clone() };
        
        if pred == SUBCLASS_URI {
            let sub_idx = self.kg.get_or_insert_node(&sub, SUBCLASS_URI);
            let obj_idx = self.kg.get_or_insert_node(&obj, SUBCLASS_URI);
            let g = self.kg.transitive_graphs.get_mut(SUBCLASS_URI).unwrap();
            g.add_edge(sub_idx, obj_idx, ());
        } else if pred == EQUIV_CLASS_URI {
            let sub_idx = self.kg.get_or_insert_node(&sub, SUBCLASS_URI);
            let obj_idx = self.kg.get_or_insert_node(&obj, SUBCLASS_URI);
            let g = self.kg.transitive_graphs.get_mut(SUBCLASS_URI).unwrap();
            g.add_edge(sub_idx, obj_idx, ());
            g.add_edge(obj_idx, sub_idx, ());
        } else if pred == DOMAIN_URI {
            self.kg.domain_map.entry(sub.clone()).or_default().push(obj.clone());
        } else if pred == RANGE_URI {
            self.kg.range_map.entry(sub.clone()).or_default().push(obj.clone());
        } else if pred == INVERSE_OF_URI {
            self.kg.inverse_of_map.insert(sub.clone(), obj.clone());
            self.kg.inverse_of_map.insert(obj.clone(), sub.clone());
        } else if pred == TYPE_URI && obj == format!("<{}>", SYMMETRIC_PROP_URI) {
            self.kg.symmetric_props.insert(sub.clone());
        } else if pred == TYPE_URI && obj == format!("<{}>", TRANSITIVE_PROP_URI) {
            self.kg.transitive_props.insert(sub.clone());
        }
        
        self.kg.triples.insert(t);
    }

    pub fn parse_content(&mut self, content: &[u8], format_hint: &str, imports_queue: &mut Vec<String>) {
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
                        self.process_triple(sub, pred, obj);
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
                        self.process_triple(sub, pred, obj);
                    }
                }
            }
            success
        };

        let first_try = format_hint == "xml";
        if !try_parse(first_try) {
            try_parse(!first_try);
        }
    }

    pub fn run_inference(&mut self) -> HashSet<Triple> {
        let mut inferred_triples: HashSet<Triple> = HashSet::new();

        // 1. Build graphs for any dynamically discovered transitive properties
        let kg_clone = self.kg.triples.clone(); // Clone to avoid borrow checker issues iterating and mutating
        for t in &kg_clone {
            let pred_with_brackets = format!("<{}>", t.pred);
            if self.kg.transitive_props.contains(&pred_with_brackets) && t.pred != SUBCLASS_URI {
                let sub_idx = self.kg.get_or_insert_node(&t.sub, &t.pred);
                let obj_idx = self.kg.get_or_insert_node(&t.obj, &t.pred);
                let g = self.kg.transitive_graphs.get_mut(&t.pred).unwrap();
                g.add_edge(sub_idx, obj_idx, ());
            }
        }

        // 2. Perform BFS transitive closures
        for (pred_uri, g) in &self.kg.transitive_graphs {
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
                        if !self.kg.triples.contains(&t) {
                            inferred_triples.insert(t);
                        }
                    }
                }
            }
        }

        // 3. Apply Domain, Range, Symmetric, Inverse rules
        for t in &self.kg.triples {
            let pred_with_brackets = format!("<{}>", t.pred);
            if let Some(domains) = self.kg.domain_map.get(&pred_with_brackets) {
                for dom in domains {
                    let inf_t = Triple { sub: t.sub.clone(), pred: TYPE_URI.to_string(), obj: dom.clone() };
                    if !self.kg.triples.contains(&inf_t) { inferred_triples.insert(inf_t); }
                }
            }
            if let Some(ranges) = self.kg.range_map.get(&pred_with_brackets) {
                if !t.obj.starts_with('"') {
                    for ran in ranges {
                        let inf_t = Triple { sub: t.obj.clone(), pred: TYPE_URI.to_string(), obj: ran.clone() };
                        if !self.kg.triples.contains(&inf_t) { inferred_triples.insert(inf_t); }
                    }
                }
            }
            if self.kg.symmetric_props.contains(&pred_with_brackets) {
                let inf_t = Triple { sub: t.obj.clone(), pred: t.pred.clone(), obj: t.sub.clone() };
                if !self.kg.triples.contains(&inf_t) { inferred_triples.insert(inf_t); }
            }
            if let Some(inv_pred) = self.kg.inverse_of_map.get(&pred_with_brackets) {
                let clean_inv_pred = inv_pred.trim_start_matches('<').trim_end_matches('>').to_string();
                let inf_t = Triple { sub: t.obj.clone(), pred: clean_inv_pred, obj: t.sub.clone() };
                if !self.kg.triples.contains(&inf_t) { inferred_triples.insert(inf_t); }
            }
        }

        inferred_triples
    }

    pub fn load_ontology(&mut self, root_file: &str, format_hint: &str) -> std::io::Result<()> {
        let mut imports_queue: Vec<String> = Vec::new();
        let mut visited_urls: HashSet<String> = HashSet::new();

        let content = fs::read(root_file)?;
        println!("Parsing root file: {}", root_file);
        self.parse_content(&content, format_hint, &mut imports_queue);
        
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

            self.parse_content(&fetched_content, "xml", &mut imports_queue);
        }

        println!("Modular parsing complete. Unified Graph Triples: {}", self.kg.triples.len());
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_transitive_property() {
        let mut engine = InferenceEngine::new();
        // Define a transitive property
        engine.process_triple("<http://example.org/prop>".to_string(), TYPE_URI.to_string(), format!("<{}>", TRANSITIVE_PROP_URI));
        
        // Assert A -> B -> C
        engine.process_triple("<http://example.org/A>".to_string(), "http://example.org/prop".to_string(), "<http://example.org/B>".to_string());
        engine.process_triple("<http://example.org/B>".to_string(), "http://example.org/prop".to_string(), "<http://example.org/C>".to_string());
        
        let inferred = engine.run_inference();
        
        let expected = Triple {
            sub: "<http://example.org/A>".to_string(),
            pred: "http://example.org/prop".to_string(),
            obj: "<http://example.org/C>".to_string(),
        };
        
        assert!(inferred.contains(&expected), "Inference should contain transitive closure A -> C");
    }

    #[test]
    fn test_symmetric_property() {
        let mut engine = InferenceEngine::new();
        engine.process_triple("<http://example.org/prop>".to_string(), TYPE_URI.to_string(), format!("<{}>", SYMMETRIC_PROP_URI));
        engine.process_triple("<http://example.org/A>".to_string(), "http://example.org/prop".to_string(), "<http://example.org/B>".to_string());
        
        let inferred = engine.run_inference();
        
        let expected = Triple {
            sub: "<http://example.org/B>".to_string(),
            pred: "http://example.org/prop".to_string(),
            obj: "<http://example.org/A>".to_string(),
        };
        
        assert!(inferred.contains(&expected), "Inference should contain symmetric link B -> A");
    }

    #[test]
    fn test_inverse_of() {
        let mut engine = InferenceEngine::new();
        engine.process_triple("<http://example.org/prop1>".to_string(), INVERSE_OF_URI.to_string(), "<http://example.org/prop2>".to_string());
        engine.process_triple("<http://example.org/A>".to_string(), "http://example.org/prop1".to_string(), "<http://example.org/B>".to_string());
        
        let inferred = engine.run_inference();
        
        let expected = Triple {
            sub: "<http://example.org/B>".to_string(),
            pred: "http://example.org/prop2".to_string(),
            obj: "<http://example.org/A>".to_string(),
        };
        
        assert!(inferred.contains(&expected), "Inference should contain inverse link B -> prop2 -> A");
    }

    #[test]
    fn test_subclass_transitivity() {
        let mut engine = InferenceEngine::new();
        engine.process_triple("<http://example.org/Dog>".to_string(), SUBCLASS_URI.to_string(), "<http://example.org/Mammal>".to_string());
        engine.process_triple("<http://example.org/Mammal>".to_string(), SUBCLASS_URI.to_string(), "<http://example.org/Animal>".to_string());
        
        let inferred = engine.run_inference();
        
        let expected = Triple {
            sub: "<http://example.org/Dog>".to_string(),
            pred: SUBCLASS_URI.to_string(),
            obj: "<http://example.org/Animal>".to_string(),
        };
        
        assert!(inferred.contains(&expected), "Inference should contain subClassOf closure Dog -> Animal");
    }

    #[test]
    fn test_domain_and_range() {
        let mut engine = InferenceEngine::new();
        engine.process_triple("<http://example.org/hasPet>".to_string(), DOMAIN_URI.to_string(), "<http://example.org/Person>".to_string());
        engine.process_triple("<http://example.org/hasPet>".to_string(), RANGE_URI.to_string(), "<http://example.org/Animal>".to_string());
        
        engine.process_triple("<http://example.org/Alice>".to_string(), "http://example.org/hasPet".to_string(), "<http://example.org/Fido>".to_string());
        
        let inferred = engine.run_inference();
        
        let expected_domain = Triple {
            sub: "<http://example.org/Alice>".to_string(),
            pred: TYPE_URI.to_string(),
            obj: "<http://example.org/Person>".to_string(),
        };
        
        let expected_range = Triple {
            sub: "<http://example.org/Fido>".to_string(),
            pred: TYPE_URI.to_string(),
            obj: "<http://example.org/Animal>".to_string(),
        };
        
        assert!(inferred.contains(&expected_domain), "Alice should be inferred as Person");
        assert!(inferred.contains(&expected_range), "Fido should be inferred as Animal");
    }
}
