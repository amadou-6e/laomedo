# Git credential protocol helper

`helper.py` is the standard-library-only Git credential helper. `main` implements
Git's external helper protocol for the currently admitted GitHub host and selected
trusted credential source. Moving it does not broaden host, grant or token scope.
Protocol output is private credential transfer, never diagnostic evidence.
