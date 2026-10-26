CXX ?= c++
CXXFLAGS ?= -O2 -std=c++17 -Wall -Wextra -Wpedantic -DNDEBUG

OBJS = passgen.o rng.o

.PHONY: all clean

all: passgen

passgen: $(OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $(OBJS)

passgen.o: passgen.cpp rng.hpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

rng.o: rng.cpp rng.hpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

clean:
	rm -f passgen $(OBJS)
