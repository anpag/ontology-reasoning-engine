import os
import pytest
import tempfile
from core.loader import OntologyLoader

@pytest.fixture
def dummy_ttl_file():
    content = """
    @prefix ex: <http://example.org/> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    @prefix owl: <http://www.w3.org/2002/07/owl#> .

    ex:Person a owl:Class .
    ex:Employee a owl:Class ;
        rdfs:subClassOf ex:Person .
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ttl", delete=False) as f:
        f.write(content)
        temp_path = f.name
        
    yield temp_path
    
    os.remove(temp_path)

def test_ontology_loader_ttl(dummy_ttl_file):
    loader = OntologyLoader()
    graph = loader.load_file(dummy_ttl_file)
    
    # Assert the graph is loaded and has triples
    assert len(graph) > 0
    assert loader.get_triple_count() == 4  # 2 class declarations + 1 subclass + 1 prefix usage (approx)
    
def test_ontology_loader_file_not_found():
    loader = OntologyLoader()
    with pytest.raises(FileNotFoundError):
        loader.load_file("non_existent_file.owl")
