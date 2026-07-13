import os
import sys

def build_imports_test():
    content = """@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix ex: <http://example.org/> .
@prefix foaf: <http://xmlns.com/foaf/0.1/> .

<http://example.org/MyOntology> a owl:Ontology ;
    owl:imports <http://xmlns.com/foaf/spec/index.rdf> .

ex:Antonio foaf:knows ex:Alice .
"""
    out_path = sys.argv[1]
    with open(out_path, "w") as f:
        f.write(content)
    print(f"Test data written to {out_path}")

if __name__ == "__main__":
    build_imports_test()
