```{include} ../../.github/CONTRIBUTING.md
:end-before: "## Also"
```

## First-time setup

- You need to install [Python](https://www.python.org/) 3 which is required for building docs.
  For example, Python 3.11.

  Then, [create and activate a virtual environment](https://docs.python.org/3/tutorial/venv.html#creating-virtual-environments).
  And install [tox](https://tox.readthedocs.io/en/latest/).

- [Install git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)

- [Configure git](https://git-scm.com/book/en/v2/Getting-Started-First-Time-Git-Setup):

  1. Please, identify yourself:

     ```console
     $ git config --global user.name "firstname lastname"
     $ git config --global user.email yourname@example.com
     ```

     Use the address bound to your GitHub account so that the commits would be linked to your profile.

  2. Choose an editor for Git:

     ```console
     $ git config --global core.editor vim
     ```

- Create and log in to a [GitHub](http://github.com) account

- [Fork](https://help.github.com/articles/fork-a-repo/) Cheroot to your GitHub account by clicking the Fork button

- [Clone](https://help.github.com/articles/cloning-a-repository/) your fork locally:

  ```console
  $ git clone https://github.com/{username}/cheroot
  $ cd cheroot
  ```

  Also, you can [clone](https://help.github.com/articles/cloning-a-repository/) fork using [ssh](https://help.github.com/articles/connecting-to-github-with-ssh/):

  ```console
  $ git clone git@github.com:{username}/cheroot.git
  $ cd cheroot
  ```

- To create a new [branch](https://www.atlassian.com/git/tutorials/using-branches) and switch to it:

  ```console
  $ git checkout -b patch/some_fix
  ```

## Write your code

- Please, use [PEP 8](https://pep8.org/)

### Once you finished coding, you are recommended to do the following steps:

- Run tests with [tox](https://tox.readthedocs.io/en/latest/)

Run one test with Python3.11:

```console
$ tox -e py311 -- cheroot/test/test_name.py
```

**`tox`** — Run all tests using the Python version where `python` command
currently points to which is specified in `tox` settings:

```ini
envlist = python
minversion = 3.21.0
```

Run linters and all tests against several Python interpreters:

```console
$ tox -e pre-commit,py310,py37  # etc.
```

- Run the [pre-commit](https://github.com/pre-commit/pre-commit) linting suite:

  ```console
  $ tox -e pre-commit
  ```

- [git add](https://git-scm.com/docs/git-add) your files

- [Write good](https://chris.beams.io/posts/git-commit/) [commit messages](https://git-scm.com/docs/git-commit) when checking in your changes to Git

- [Push](https://git-scm.com/docs/git-push) and [create a pull request](https://help.github.com/articles/creating-a-pull-request/)

## Building the docs

To build the docs from a checked out source, run:

```console
$ tox -e build-docs
```

Open the documentation:

`````{tabs}
````{tab} GNU/Linux
```console
$ xdg-open build/html/index.html
```
````

````{tab} macOS
```console
$ open build/html/index.html
```
````

````{tab} Windows
Please, open `build/html/index.html` in your browser.
````
`````

Also, one can serve docs using a built-in static files server.
This is preferable because of possible CSRF issues.

```console
$ python3 -m http.server --directory build/html/ 8000
```

After that, you can open [http://localhost:8000/](http://localhost:8000/) in your browser.

Read more about [Sphinx](https://www.sphinx-doc.org).

```{include} ../changelog-fragments.d/README.md
```
