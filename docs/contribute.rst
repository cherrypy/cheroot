.. include:: ../.github/CONTRIBUTING.rst


First-time setup
~~~~~~~~~~~~~~~~

- `Install git`_

- `Configure git`_:

1. Please identify yourself::

        $ git config --global user.name "firstname lastname"

        $ git config --global user.email yourname@example.com

2. Chose editor for git commit::

        $ git config --global core.editor vim

- Create and log in in `GitHub`_ account Create ang log in in `github`_ account

- `Fork`_ Cheroot to your GitHub account it just needs clicking the Fork button

- `Clone`_ your fork locally::

        git clone https://github.com/{username}/cheroot

        cd cheroot

- To create a new `branch`_ and switch to it::

        git checkout -b patch/some_fix

.. _Install git: https://git-scm.com/book/en/v2/Getting-Started-Installing-Git
.. _Configure git: https://git-scm.com/book/en/v2/Getting-Started-First-Time-Git-Setup
.. _GitHub: http://github.com
.. _Fork: https://help.github.com/articles/fork-a-repo/
.. _Clone: https://help.github.com/articles/cloning-a-repository/
.. _branch: https://www.atlassian.com/git/tutorials/using-branches

Write your code
~~~~~~~~~~~~~~~

- Please to use `pep8`_

After then you finished the code you need to do some steps:
"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

- Run tests with `tox`_

Run one test with Python3.6::

        tox -e py36 -- cheroot/test/test_name.py

**`tox`** - Run all tests for the environment, who wrote in tox settings::

        envlist = python
        minversion = 3.5.3

run with all Python interpreter:: 

        tox -e pre-commit,py27,py37 etc

- Run the `pre-commit`_::

        tox -e pre-commit - run pre-commit

- `git add`_ your files

- `Write good`_ `git commit`_ for your code

- `Push`_ and `to create a pull request`_

.. _tox: https://tox.readthedocs.io/en/latest/
.. _git commit: https://git-scm.com/docs/git-commit
.. _Write good: https://chris.beams.io/posts/git-commit/
.. _Push: https://git-scm.com/docs/git-push
.. _git add: https://git-scm.com/docs/git-add
.. _to create a pull request: https://help.github.com/articles/creating-a-pull-request/
.. _pep8: https://pep8.org/
.. _pre-commit: https://github.com/pre-commit/pre-commit

Building the docs
~~~~~~~~~~~~~~~~~

Building documentation::

        tox -e build-docs

Open the documentation::

        firefox build/html/index.html

Read more about `Sphinx`_.

.. _Sphinx: https://www.sphinx-doc.org
