CC ?= cc
CFLAGS ?= -O2 -std=gnu11 -Wall -Wextra -Wpedantic -DNDEBUG

OBJS = passgen.o rng.o

.PHONY: all clean

all: passgen

passgen: $(OBJS)
	$(CC) $(CFLAGS) -o $@ $(OBJS)

passgen.o: passgen.c rng.h
	$(CC) $(CFLAGS) -c $< -o $@

rng.o: rng.c rng.h
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f passgen $(OBJS)
