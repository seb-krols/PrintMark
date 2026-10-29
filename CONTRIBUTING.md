# Contributing

Thanks for helping. Bug reports, print results and ideas are welcome as
[issues](https://github.com/seb-krols/PrintMark/issues). Useful details: PrusaSlicer
version, printer and print preset, the notice BaseMark showed, and if possible the exported
G-code (without printer-host settings).

## Pull requests

BaseMark is free for noncommercial use and offered under paid licenses for commercial use
(see [LICENSING.md](LICENSING.md)). So that every part of it can be offered both ways:

**By opening a pull request, you confirm that you wrote the contribution (or have the right
to submit it) and you allow Sebastians Krols to distribute it under the PolyForm
Noncommercial License 1.0.0 and under commercial licenses.** If you don't want that, please
open an issue describing the change instead.

For larger changes, open an issue first so we can agree on the approach. Before submitting:

```sh
uv sync --extra dev
uv run ruff check .
uv run pytest
```
