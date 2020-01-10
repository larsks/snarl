# Snarl: Literate programming with Markdown

Snarl is a [literate programming][] tool for Markdown documents.  The syntax was inspired by [Anansi][].

## Syntax

### Code blocks

Code blocks are defined using a modified version the standard Markdown syntax for fenced code blocks.

<pre>
```[lang]:label [hide]
...your code goes here...
```
</pre>

Everything after the `:` is stripped when weaving, leaving a standard fenced code block. For example, to define a code block named `imports` you could write:

<pre>
```python:imports
import os
import sys
```
</pre>

When weaving, this would be rendered as:

<pre>
```python
import os
import sys
```
</pre>

Marking a code block with `hide` will hide it when generating output with `weave`, but you can still refer to it in a `:file` block.

### Writing files

Declare a file to be written during the `tangle` process using the `:file` directive. The contents between the `:file` directive and the terminating `:` will be written to the named file.

Include named blocks in the output by enclosing the block name in `|`.

For example:

```
:file somefile.py
# Here are my imports
|imports|
:
```

Assuming we have defined the `imports` block as described earlier, running `snarl tangle` on this file would generate a file named `somefile.py` with the content:

```
# Here are my imports
import os
import sys
```

### Including files

Include files with the `:include` directive:

```
:include some_file.md
```

The contents of the named file will be processed as if they occurred in the main document at the point of the `:include` directive. This means you can include `snarl` syntax in your included files.

### Comments

A line starting with `:#` is ignored.

```
:# This is a comment.
```

[literate programming]: https://en.wikipedia.org/wiki/Literate_programming
[anansi]: https://john-millikin.com/software/anansi
