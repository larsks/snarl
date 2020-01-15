# Snarl: Literate programming with Markdown

Snarl is a [literate programming][] tool for Markdown documents.

[literate programming]: https://en.wikipedia.org/wiki/Literate_programming

## Features

- Literate programming while keeping your markdown editor happy.
- Label your code blocks for use in generating files.
- Generate files using named code blocks and verbatim content. Blocks
  can be assembled out-of-order.
- Include files to split a large document across multiple files.

## Syntax

### Code blocks

Code blocks are defined using a modified version the standard Markdown syntax for fenced code blocks.

<pre>
```[lang]=label [--hide] [--file] [--replace *pattern* *substitution*]
...your code goes here...
```
</pre>

Everything after the `=` is stripped when weaving, leaving a standard fenced code block.

The following options are available:

- `--hide` -- causes snarl to ignore the code block when weaving.
- `--file` -- marks the block as a file that should be generated when tangling.
- `--replace *pattern* *substitution*` -- when tangling, replace
  _pattern_ with _subsitution_.

To include content from one code block in another code block when tangling, refer to it using `<<...>>` markers. For example:

<!-- Since I'm using <pre> blocks to wrap the markdown example, I need to escape
     all instances of < with &gt;. -->
<pre>
```=hello.c --file
&lt;&lt;includes>>

int main() {
&lt;&lt;body of main function>>
}
```
</pre>

### Including files

Include files with the `<!-- include ... -->` directive:

```
<!-- include some_file.md -->
```

The contents of the named file will be processed as if it occurred in the main document at the point of the `<!-- include ... -->` directive. This means you can include `snarl` syntax in your included files.
