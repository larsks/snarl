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

Code blocks are defined using a modified version the standard Markdown syntax for fenced code blocks:

<pre>
```[lang]=label [options]
...your code goes here...
```
</pre>

Everything after the `=` (or `+=`) is stripped when weaving, leaving a standard fenced code block.

The following options are available:

- `--hide` -- causes snarl to ignore the code block when weaving.
- `--file` -- marks the block as a file that should be generated when tangling.
- `--replace *pattern* *substitution*` -- when tangling, replace
  _pattern_ with _subsitution_.
- `--tag *tag*` -- assign a tag to a block, which can be used to select sets
  of files when tangling. May be specified multiple times.
- `--escape-html` -- escape characters in the code block that would cause undesirable behavior when rendered to HTML.
- `--verbatim` -- do not process `<<...>>` blocks in the code block

There is alternate syntax used to append content to an existing code block:

<pre>
```[lang]+=label
...your code goes here...
```
</pre>

You can't set options on an appended block (it becomes part of the previously declared block).

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
<!-- include *path* [--escape-html] [--verbatim] -->
```

The contents of the named file will be processed as if it occurred in the main document at the point of the `<!-- include ... -->` directive. This means you can include `snarl` syntax in your included files.

The following options are available:

- `--escape-html` -- escape characters that will cause problems when rendered to HTML (such as `<` and `&`).
- `--verbatim` -- insert the content without processing it for snarl directives.

## See also

- I wrote a [blog post][] about this tool.

[blog post]: https://blog.oddbit.com/post/2020-01-15-snarl-a-tool-for-literate-blog/
