import os
from rdflib import Graph
import tempfile
import owlready2
import logging

class OntologyReasoner:
    """
    Applies deductive reasoning to an ontology graph.
    Designed to be pluggable with different reasoning backends (e.g. C++ FaCT++, HermiT).
    """
    
    def __init__(self, backend="hermit"):
        self.backend = backend
        
    def materialize(self, graph: Graph) -> Graph:
        """
        Takes a base graph, applies reasoning, and returns the expanded graph
        containing both explicit and implicitly inferred triples.
        """
        if self.backend == "hermit":
            return self._run_hermit(graph)
        elif self.backend == "factpp":
            return self._run_factpp(graph)
        else:
            raise ValueError(f"Unknown reasoning backend: {self.backend}")
            
    def _run_hermit(self, graph: Graph) -> Graph:
        """
        Fallback Java-based reasoning via owlready2 (HermiT).
        Requires serializing the rdflib graph to disk temporarily.
        """
        logging.info("Starting HermiT reasoning engine...")
        # Write rdflib graph to temp xml
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xml") as temp_xml:
            graph.serialize(destination=temp_xml.name, format="xml")
            temp_xml_path = temp_xml.name
            
        try:
            # Load into owlready2
            world = owlready2.World()
            onto = world.get_ontology(f"file://{temp_xml_path}").load()
            
            # Reason
            with onto:
                owlready2.sync_reasoner(world, debug=0)
                
            # Save reasoned ontology back to temp
            reasoned_xml_path = temp_xml_path + "_reasoned.xml"
            onto.save(file=reasoned_xml_path, format="rdfxml")
            
            # Load back to rdflib
            expanded_graph = Graph()
            expanded_graph.parse(reasoned_xml_path, format="xml")
            
            # Cleanup
            os.remove(reasoned_xml_path)
            return expanded_graph
            
        finally:
            if os.path.exists(temp_xml_path):
                os.remove(temp_xml_path)

    def _run_factpp(self, graph: Graph) -> Graph:
        """
        Executes the C++ FaCT++ reasoning engine via a highly concurrent subprocess.
        This bypasses the JVM entirely and uses the native OS binary.
        """
        logging.info("Starting C++ FaCT++ reasoning engine...")
        import subprocess
        
        # 1. Serialize the graph for the C++ binary
        with tempfile.NamedTemporaryFile(delete=False, suffix=".owl") as temp_in:
            graph.serialize(destination=temp_in.name, format="xml")
            in_path = temp_in.name
            
        out_path = in_path + "_reasoned.owl"
        
        try:
            # 2. Invoke the compiled C++ binary (e.g. fact++-cli)
            # We assume the binary is available in the system PATH as 'fact++-cli'
            # The exact flags depend on the compiled binary's interface.
            cmd = ["fact++-cli", "--materialize", "--input", in_path, "--output", out_path]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logging.error(f"FaCT++ C++ Engine Failed:\n{result.stderr}")
                raise RuntimeError("C++ Reasoning Engine failed to execute.")
                
            # 3. Load the highly optimized output back into RDFLib
            expanded_graph = Graph()
            expanded_graph.parse(out_path, format="xml")
            
            return expanded_graph
            
        except FileNotFoundError:
            raise NotImplementedError("The C++ binary 'fact++-cli' was not found on this system. It must be compiled and added to PATH.")
        finally:
            if os.path.exists(in_path):
                os.remove(in_path)
            if os.path.exists(out_path):
                os.remove(out_path)
