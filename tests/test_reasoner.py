import pytest
from rdflib import Graph, Namespace, RDF, RDFS
from core.reasoner import OntologyReasoner

def test_reasoner_hermit_subclass_inference():
    # Create a simple hierarchy: A subclass of B, B subclass of C
    # The reasoner should mathematically infer that A is a subclass of C
    g = Graph()
    ex = Namespace("http://example.org/")
    owl = Namespace("http://www.w3.org/2002/07/owl#")
    
    # We must explicitly type them as OWL Classes for HermiT to process them
    g.add((ex.ClassA, RDF.type, owl.Class))
    g.add((ex.ClassB, RDF.type, owl.Class))
    g.add((ex.ClassC, RDF.type, owl.Class))
    
    # Add explicit SubClass logic
    g.add((ex.ClassA, RDFS.subClassOf, ex.ClassB))
    g.add((ex.ClassB, RDFS.subClassOf, ex.ClassC))
    
    # Ensure the implicit relationship does not exist yet
    assert (ex.ClassA, RDFS.subClassOf, ex.ClassC) not in g
    
    # Run the materialization
    reasoner = OntologyReasoner(backend="hermit")
    expanded_g = reasoner.materialize(g)
    
    # After reasoning, ClassA -> subClassOf -> ClassC MUST exist mathematically
    assert (ex.ClassA, RDFS.subClassOf, ex.ClassC) in expanded_g

def test_reasoner_factpp_not_implemented():
    reasoner = OntologyReasoner(backend="factpp")
    with pytest.raises(NotImplementedError):
        reasoner.materialize(Graph())
