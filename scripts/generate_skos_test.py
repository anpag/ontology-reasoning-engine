import rdflib
import sys

def build_test_data():
    g = rdflib.Graph()
    print("Downloading and parsing the official W3C SKOS Ontology...")
    # SKOS defines exactMatch (Symmetric), broader/narrower (Inverse), and broaderTransitive (Transitive)
    g.parse("http://www.w3.org/2004/02/skos/core", format="xml")

    ex = rdflib.Namespace("http://example.org/data/")
    skos = rdflib.Namespace("http://www.w3.org/2004/02/skos/core#")

    print("Injecting real-world ABox instance data to test inference...")
    # 1. Symmetric Test (exactMatch)
    g.add((ex.CompanyA, skos.exactMatch, ex.CompanyB))

    # 2. Inverse Test (broader <-> narrower)
    g.add((ex.MachineLearning, skos.broader, ex.ArtificialIntelligence))

    # 3. Transitive Test (broaderTransitive)
    g.add((ex.DeepLearning, skos.broaderTransitive, ex.MachineLearning))
    g.add((ex.MachineLearning, skos.broaderTransitive, ex.ArtificialIntelligence))

    out_path = sys.argv[1]
    g.serialize(destination=out_path, format="turtle")
    print(f"Test data written to {out_path}")

if __name__ == "__main__":
    build_test_data()
