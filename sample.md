# Snarl example

This document is an example of the syntax supported by [snarl][].

[snarl]: https://github.com/larsks/snarl

## Printing Hello world

To print the text `Hello, world!` on the console, we can use the following statement:

```c="body of main function"
  printf("Hello, world!\n");
```

Because we're using the `printf` function, we need to include the `stdio.h` header file which includes the `printf` function prototype:

```c=includes
#include <stdio.h>
```

Putting this all together, we end up with a source file that looks something like:

```c=hello.c --file
<<includes>>

int main(int argc, char **argv) {
<<body of main function>>
}
```

We can build this by running `gcc -o hello hello.c`.

```=Makefile --file --hide
hello: hello.o
	$(CC) -o $@ $<

sample.w.md: sample.md
	snarl weave -o $@ $<

sample.html: sample.w.md
	pandoc -o $@ $<
  
```

```=test_hello.sh --hide --file
#!/bin/bash

tmpfile=$(mktemp expected.XXXXXX)
trap "rm -f $tmpfile" EXIT

cat > $tmpfile <<EOF
Hello, world!
EOF

make
if ! diff -u <(./hello) $tmpfile; then
  echo "FAILED"
  exit 1
else
  echo "SUCCESS"
fi

exit 0
```
