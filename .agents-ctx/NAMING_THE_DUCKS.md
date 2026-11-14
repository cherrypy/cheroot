# Naming the Ducks

Canonical names for this project, and how to refer to it in
prose. Other files in `.agents-ctx/` (and any generated content)
should say "the project" rather than hardcoding one of these --
reach for a specific name only when the distinction actually
matters (e.g. citing a package, an import, or a repository URL).

## Distribution / PyPI name: `cheroot`

The installable, published name -- recorded in
`pyproject.toml`'s `[project].name` per PEP 621. This is also
the preferred way to refer to the project by name in prose,
capitalized as "Cheroot" at the start of a sentence.

## Python import name: `cheroot`

The same as the distribution name. The test suite ships inside
it, as `cheroot.test`.

## GitHub repository slug: `cherrypy/cheroot`

Use it verbatim when it's actually the repository being
referenced (URLs, `gh` invocations, PR/issue citations) -- not as
a stand-in for the project's name in prose.

## Don't confuse it with CherryPy

Cheroot is the HTTP server that CherryPy, published from
`cherrypy/cherrypy`, runs on. The two live in separate
repositories and are released separately. Say which one is meant.
