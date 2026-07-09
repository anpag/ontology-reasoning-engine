#include <iostream>
#include <fstream>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

using namespace std;

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

    string input_file = argv[1];
    string output_file = argv[2];

    ifstream infile(input_file);
    if (!infile.is_open()) {
        cerr << "Failed to open input file.\n";
        return 1;
    }

    unordered_map<string, vector<string>> subclass_graph;
    string subClassOf_uri = "<http://www.w3.org/2000/01/rdf-schema#subClassOf>";

    string line;
    while (getline(infile, line)) {
        if (line.empty()) continue;
        string sub, pred, obj;
        if (parse_ntriple(line, sub, pred, obj)) {
            // Only tracking subclass for transitive closure in V1
            if (pred == subClassOf_uri) {
                subclass_graph[sub].push_back(obj);
            }
        }
    }
    infile.close();

    ofstream outfile(output_file);
    int inferred_count = 0;

    // 1. Compute Transitive Closure for SubClassOf using BFS
    // This allows us to mathematically infer that A is a subclass of C if A->B and B->C
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
                    
                    // Output the inferred triple back in N-Triples format
                    outfile << start_node << " " << subClassOf_uri << " " << neighbor << " .\n";
                    inferred_count++;
                }
            }
        }
    }
    
    outfile.close();
    cout << "Custom C++ Engine Materialization Complete. Inferred " << inferred_count << " subclass relations.\n";
    return 0;
}
