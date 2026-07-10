#include <iostream>
#include <fstream>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

using namespace std;

// Constants for OWL/RDFS vocabulary
const string SUBCLASS_URI = "<http://www.w3.org/2000/01/rdf-schema#subClassOf>";
const string TYPE_URI = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>";
const string DOMAIN_URI = "<http://www.w3.org/2000/01/rdf-schema#domain>";
const string RANGE_URI = "<http://www.w3.org/2000/01/rdf-schema#range>";
const string EQUIV_CLASS_URI = "<http://www.w3.org/2002/07/owl#equivalentClass>";

// A triple structure for the graph
struct Triple {
    string sub, pred, obj;
    bool operator==(const Triple& other) const {
        return sub == other.sub && pred == other.pred && obj == other.obj;
    }
};

// Hash function for Triples
namespace std {
    template <>
    struct hash<Triple> {
        size_t operator()(const Triple& k) const {
            return hash<string>()(k.sub) ^ (hash<string>()(k.pred) << 1) ^ (hash<string>()(k.obj) << 2);
        }
    };
}

// Parses a simple N-Triple line: <sub_uri> <pred_uri> <obj_uri> .
bool parse_ntriple(const string& line, string& sub, string& pred, string& obj) {
    size_t first_space = line.find(' ');
    size_t second_space = line.find(' ', first_space + 1);
    size_t dot_pos = line.rfind(" .");
    
    if (first_space != string::npos && second_space != string::npos && dot_pos != string::npos) {
        sub = line.substr(0, first_space);
        pred = line.substr(first_space + 1, second_space - first_space - 1);
        obj = line.substr(second_space + 1, dot_pos - second_space - 1); 
        return true;
    }
    return false;
}

int main(int argc, char* argv[]) {
    if (argc < 3) {
        cerr << "Usage: custom_reasoner <input.nt> <output.nt>\n";
        return 1;
    }

    ifstream infile(argv[1]);
    if (!infile.is_open()) return 1;

    unordered_set<Triple> graph;
    unordered_map<string, vector<string>> subclass_graph;
    unordered_map<string, vector<string>> domain_map;
    unordered_map<string, vector<string>> range_map;
    
    string line;
    while (getline(infile, line)) {
        if (line.empty()) continue;
        string sub, pred, obj;
        if (parse_ntriple(line, sub, pred, obj)) {
            graph.insert({sub, pred, obj});
            
            if (pred == SUBCLASS_URI) subclass_graph[sub].push_back(obj);
            if (pred == EQUIV_CLASS_URI) {
                subclass_graph[sub].push_back(obj);
                subclass_graph[obj].push_back(sub);
            }
            if (pred == DOMAIN_URI) domain_map[sub].push_back(obj);
            if (pred == RANGE_URI) range_map[sub].push_back(obj);
        }
    }
    infile.close();

    unordered_set<Triple> inferred_triples;

    // Rule 1: Transitive Closure for SubClassOf (BFS)
    for (const auto& pair : subclass_graph) {
        const string& start_node = pair.first;
        unordered_set<string> visited;
        vector<string> queue;
        
        queue.push_back(start_node);
        visited.insert(start_node);
        
        size_t head = 0;
        while(head < queue.size()) {
            string current = queue[head++];
            for (const string& neighbor : subclass_graph[current]) {
                if (visited.find(neighbor) == visited.end()) {
                    visited.insert(neighbor);
                    queue.push_back(neighbor);
                    Triple t = {start_node, SUBCLASS_URI, neighbor};
                    if (graph.find(t) == graph.end()) inferred_triples.insert(t);
                }
            }
        }
    }

    // Rule 2 & 3: Domain and Range Type Inference
    for (const Triple& t : graph) {
        // If property has a domain, subject becomes that type
        if (domain_map.count(t.pred)) {
            for (const string& dom : domain_map[t.pred]) {
                Triple inf_t = {t.sub, TYPE_URI, dom};
                if (graph.find(inf_t) == graph.end()) inferred_triples.insert(inf_t);
            }
        }
        // If property has a range, object becomes that type (if object is a URI)
        if (range_map.count(t.pred) && t.obj[0] == '<') {
            for (const string& ran : range_map[t.pred]) {
                Triple inf_t = {t.obj, TYPE_URI, ran};
                if (graph.find(inf_t) == graph.end()) inferred_triples.insert(inf_t);
            }
        }
    }

    ofstream outfile(argv[2]);
    for (const Triple& t : inferred_triples) {
        outfile << t.sub << " " << t.pred << " " << t.obj << " .\n";
    }
    outfile.close();
    
    cout << "Custom Engine Materialization Complete. Inferred " << inferred_triples.size() << " triples.\n";
    return 0;
}
