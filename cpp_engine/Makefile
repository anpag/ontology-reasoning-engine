CXX = g++
CXXFLAGS = -O3 -std=c++17 -Wall

all: custom_reasoner

custom_reasoner: reasoner.cpp
	$(CXX) $(CXXFLAGS) -o custom_reasoner reasoner.cpp

clean:
	rm -f custom_reasoner
