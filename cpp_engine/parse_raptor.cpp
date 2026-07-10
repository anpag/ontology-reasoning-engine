#include <raptor2.h>
#include <iostream>
#include <chrono>

using namespace std;

// Empty statement handler for raptor (we just want to measure parsing speed)
void statement_handler(void* user_data, raptor_statement* statement) {
    long* count = (long*)user_data;
    (*count)++;
}

int main(int argc, char* argv[]) {
    if (argc < 3) {
        cerr << "Usage: parse_raptor <file_path> <format (rdfxml|turtle)>\n";
        return 1;
    }

    // Convert file path to file URI for Raptor
    string file_path = string("file://") + argv[1];
    const char* format = argv[2];

    raptor_world* world = raptor_new_world();
    raptor_parser* rdf_parser = raptor_new_parser(world, format);
    
    long triple_count = 0;
    raptor_parser_set_statement_handler(rdf_parser, &triple_count, statement_handler);
    
    raptor_uri* uri = raptor_new_uri(world, (const unsigned char*)file_path.c_str());
    raptor_uri* base_uri = raptor_uri_copy(uri);

    cout << "\n--- Testing Raptor2 (Pure C++) ---" << endl;
    
    auto start = chrono::high_resolution_clock::now();
    
    raptor_parser_parse_file(rdf_parser, uri, base_uri);
    
    auto end = chrono::high_resolution_clock::now();
    chrono::duration<double> elapsed = end - start;
    
    cout << "Raptor2 parsed " << triple_count << " triples in " << elapsed.count() << " seconds.\n";

    raptor_free_parser(rdf_parser);
    raptor_free_uri(base_uri);
    raptor_free_uri(uri);
    raptor_free_world(world);

    return 0;
}
