"""PyInstaller entry point; keep imports absolute for frozen execution."""

from basemark.__main__ import main

raise SystemExit(main())
